"""STEP 2: step 1 plus three small fixes. Still one script. Still no queue, no database server, no web screen.

Everything else from step 1 is here unchanged: the forms for each kind of UC1 paper and the readers
for PDF, scanned PDF, Excel, photo and JSON. What step 1 got wrong, and the plain fix for each:
  1. The form was picked from the FILE NAME          ->  ask first: what kind of paper is this? Then use the matching form.
     (Real uploads are not named for you. Even in the sample pack, proformas are called invoice.pdf.)
  2. Running it twice pays for every model call twice  ->  fingerprint each file (SHA-256) and skip files we have seen.
  3. A crash loses everything read so far             ->  save each result to a file the moment it exists.

Run it, stop it half way (Ctrl-C), run it again: the second run picks up where the first stopped.
See only what changed:  diff ladder/step1_one_agent.py ladder/step2_three_small_fixes.py

Run:  ./run.sh ladder/step2_three_small_fixes.py data/uc1_supplier_payments/PAY-202611008
      ./run.sh ladder/step2_three_small_fixes.py data/uc1_supplier_payments/PAY-2026110*

The kinds use the doc_type labels in data/uc1_supplier_payments/ground_truth.json, so they can be scored.
The payment instruction still skips the model: it arrives as JSON from the client portal, so where it came
from already says what it is.

What the fingerprint does NOT catch: the same invoice uploaded again as a different file (a new scan,
a copy). The bytes differ, so the hash differs. That is the POSSIBLE_DUPLICATE check, which compares
what the papers say, not their bytes; it comes with the checks in a later step.
"""
import base64
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Literal

import pandas as pd
import pypdfium2 as pdfium
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from pypdf import PdfReader

DATE = "YYYY-MM-DD"


# ---------------------------------------------------------------------------------------------
# The forms: one per kind of paper in a UC1 case (spec, "Documents per payment").
# Where a field feeds a UC1 check, its name follows expected_fields in
# data/uc1_supplier_payments/ground_truth.json, so a later step can score it.
# ---------------------------------------------------------------------------------------------

class Bank(BaseModel):
    bank_name: str = ""
    bank_country: str = ""
    swift: str = ""
    account_number: str | None = None
    iban: str | None = None
    clabe: str | None = None  # Mexico
    ifsc: str | None = None   # India
    cnaps: str | None = None  # China


class Beneficiary(BaseModel):
    beneficiary_id: str
    name: str
    address: str = ""
    country: str
    bank: Bank


class PaymentInstruction(BaseModel):
    """From the client portal, as JSON. Read by plain code, not by the model."""
    payment_id: str
    submitted_at: str
    client_id: str
    client_name: str
    beneficiary: Beneficiary
    amount: float
    currency: str
    purpose_code: str = Field(description="GDI goods, ADV advance, SVC services")
    invoice_references: list[str] = []
    remittance_info: str = ""
    requested_value_date: str = ""


class Invoice(BaseModel):
    """Supplier invoice (commercial or service) or proforma invoice."""
    invoice_number: str = ""
    invoice_date: str = Field("", description=DATE)
    due_date: str = Field("", description=DATE)
    seller: str = Field("", description="the supplier issuing the invoice")
    buyer: str = Field("", description="the company the invoice is addressed to")
    po_number: str = Field("", description="purchase order reference, if printed")
    contract_number: str = Field("", description="services contract reference, if printed")
    invoice_total: float = 0
    invoice_currency: str = Field("", description="ISO code, e.g. USD")
    invoice_bank_account: str = Field("", description="pay-to account / IBAN / CLABE printed on the invoice")
    invoice_signatory: str = ""
    is_proforma: bool = Field(False, description="true if marked proforma (advance payment)")


class PurchaseOrder(BaseModel):
    po_number: str = ""
    po_date: str = Field("", description=DATE)
    buyer: str = ""
    supplier: str = ""
    po_currency: str = Field("", description="ISO code")
    po_total: float = 0
    approved_by: str = ""


class ServicesContract(BaseModel):
    contract_number: str = Field("", description="agreement / contract number")
    effective_date: str = Field("", description=DATE)
    provider: str = Field("", description="the supplier providing the services")
    client: str = Field("", description="the company receiving the services")
    scope: str = ""
    contract_value: float = 0
    contract_currency: str = Field("", description="ISO code")
    term: str = ""
    billing: str = ""
    provider_signatory: str = ""
    client_signatory: str = ""


class BankDetailsLetter(BaseModel):
    letter_type: str = Field("", description="CHANGE if it announces new details, CONFIRMATION if it re-confirms them")
    letter_date: str = Field("", description=DATE)
    supplier: str = Field("", description="the company sending the letter")
    addressed_to: str = ""
    account_holder: str = ""
    bank_name: str = ""
    bank_country: str = Field("", description="ISO 2-letter code")
    bank_letter_account: str = Field("", description="account number / IBAN / CLABE in the letter")
    swift: str = ""
    local_code: str = Field("", description="IFSC, CNAPS or other local bank code, if printed")
    effective_date: str = Field("", description=DATE)
    signatory: str = ""


class Bundle(BaseModel):
    """One scan holding an invoice and its purchase order."""
    invoice: Invoice
    purchase_order: PurchaseOrder


# FIX 1: ask what kind of paper it is, then pick the form. The step 1 file-name list is gone.
class Kind(BaseModel):
    kind: Literal[
        "COMMERCIAL_INVOICE",     # an invoice for goods or services, asking to be paid
        "PROFORMA_INVOICE",       # marked proforma: a quote asking for an advance payment
        "PURCHASE_ORDER",         # issued by the buyer, ordering goods
        "SERVICES_CONTRACT",      # an agreement for services: parties, scope, value, term
        "BANK_DETAILS_LETTER",    # a supplier letter changing or confirming its bank account
        "INVOICE_AND_PO_BUNDLE",  # one file holding an invoice AND a purchase order
        "OTHER",
    ] = Field(description="What kind of paper this is. Look at every page.")


FORMS: dict[str, type[BaseModel]] = {
    "COMMERCIAL_INVOICE": Invoice,
    "PROFORMA_INVOICE": Invoice,  # same form; is_proforma says which
    "PURCHASE_ORDER": PurchaseOrder,
    "SERVICES_CONTRACT": ServicesContract,
    "BANK_DETAILS_LETTER": BankDetailsLetter,
    "INVOICE_AND_PO_BUNDLE": Bundle,
}


# ---------------------------------------------------------------------------------------------
# The agent: a model, no tools, and a form to fill. Same recipe for every form.
# ---------------------------------------------------------------------------------------------

model = ChatGoogleGenerativeAI(model=os.environ.get("MODEL_SMALL", "gemini-3.5-flash-lite"))
agents = {}


FILL = (
    "You read the papers behind cross-border supplier payments. Fill the form from the paper. "
    "Copy numbers, references and account numbers exactly. Leave a field empty if it is not printed."
)
CLASSIFY = "You sort the papers behind cross-border supplier payments. Say what kind of paper this is. Look at every page."


def agent_for(form: type[BaseModel], prompt: str = FILL):
    if form not in agents:
        agents[form] = create_agent(model, tools=[], system_prompt=prompt, response_format=ToolStrategy(form))
    return agents[form]


def ask(form: type[BaseModel], content: list, prompt: str = FILL) -> BaseModel:
    return agent_for(form, prompt).invoke({"messages": [HumanMessage(content=content)]})["structured_response"]


# ---------------------------------------------------------------------------------------------
# Turning a file into something the model can read.
# ---------------------------------------------------------------------------------------------

def image_part(data: bytes, mime: str) -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64," + base64.b64encode(data).decode()}}


def read_file(path: str) -> list:
    """Text where the file has text, pictures where it does not."""
    suffix = Path(path).suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png"):
        return [image_part(Path(path).read_bytes(), "image/png" if suffix == ".png" else "image/jpeg")]
    if suffix == ".xlsx":  # an Excel invoice: every sheet as plain text
        sheets = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
        text = "\n\n".join(f"Sheet {name}\n" + df.fillna("").to_csv(index=False, header=False) for name, df in sheets.items())
        return [{"type": "text", "text": text}]
    text = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    if len(text.strip()) > 40:
        return [{"type": "text", "text": text}]
    parts = []  # a scan: send every page as a picture
    for page in pdfium.PdfDocument(path):
        buf = io.BytesIO()
        page.render(scale=2).to_pil().convert("L").save(buf, format="PNG")
        parts.append(image_part(buf.getvalue(), "image/png"))
    return parts


def read_paper(path: str) -> tuple[str, BaseModel | None]:
    """Returns (kind, filled form). Two model calls: what is it, then fill its form."""
    if Path(path).suffix.lower() == ".json":
        return "PAYMENT_INSTRUCTION", PaymentInstruction.model_validate_json(Path(path).read_text())
    content = read_file(path)  # read (and render scans) once, use for both calls
    kind = ask(Kind, content, CLASSIFY).kind  # fix 1
    if kind not in FORMS:
        return kind, None
    return kind, ask(FORMS[kind], content)


def papers(path: str) -> list[str]:
    """A file is one paper; a case folder is all of its papers."""
    p = Path(path)
    return [path] if p.is_file() else [str(f) for f in sorted(p.iterdir()) if f.is_file()]


# ---------------------------------------------------------------------------------------------
# FIXES 2 AND 3: fingerprint each file, and save each result as soon as it exists.
# ---------------------------------------------------------------------------------------------

SAVED = Path(os.environ.get("STEP2_RESULTS", "ladder/results.jsonl"))  # one line per paper read


def fingerprint(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_saved() -> dict:
    """Everything earlier runs read, by fingerprint. A line cut short by a crash is ignored, so that paper is read again."""
    done = {}
    if SAVED.exists():
        for line in SAVED.read_text().splitlines():
            try:
                row = json.loads(line)
                done[row["sha256"]] = row
            except (json.JSONDecodeError, KeyError):
                pass
    return done


def save(row: dict) -> None:
    """Fix 3: append and flush now, not at the end of the run."""
    SAVED.parent.mkdir(parents=True, exist_ok=True)
    cut_short = SAVED.exists() and SAVED.stat().st_size > 0 and not SAVED.read_bytes().endswith(b"\n")
    with SAVED.open("a") as out:
        out.write(("\n" if cut_short else "") + json.dumps(row, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())


def read_once(path: str, done: dict) -> tuple[dict, bool]:
    """Returns (row, seen_before). Fix 2: the same bytes are never sent to the model twice."""
    sha = fingerprint(path)
    if sha in done:
        return done[sha], True
    kind, paper = read_paper(path)
    row = {
        "file": path,
        "case_id": Path(path).parent.name,
        "sha256": sha,
        "kind": kind,
        "form": type(paper).__name__ if paper else None,
        "fields": paper.model_dump() if paper else {},
        "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save(row)
    done[sha] = row
    return row, False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    done = load_saved()
    read = seen = 0
    for arg in sys.argv[1:]:
        for path in papers(arg):
            started = time.time()
            row, seen_before = read_once(path, done)
            label = f"{path}   {row['kind']} -> {row['form'] or 'no form'}"
            if seen_before:
                seen += 1
                same = "" if row["file"] == path else f" as {row['file']}"
                print(f"{label}   seen before{same}, not read again")
            else:
                read += 1
                print(f"{label}   read and saved   ({time.time() - started:.1f} s)")
    print(f"\n{read} read, {seen} seen before. Results: {SAVED}")
