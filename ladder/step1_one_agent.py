"""STEP 1: the simplest thing that could work, on UC1 supplier invoice payments.

One agent recipe: a small model, no tools, and a form to fill. Each kind of paper in a UC1 case
gets its own form (a Pydantic model below). Give it a file or a whole case folder and it prints
the fields off every paper. Nothing else: no checks that the papers agree, no queue, no database,
no screen. It is the first version anyone would write.

Two shortcuts that later steps remove:
  - The form is picked from the FILE NAME. Real uploads are not named for you; step 2 adds a
    classifier that looks at the paper instead.
  - The payment instruction is already JSON from the client portal, so plain code reads it.
    No model is needed to read data that is already structured.

The papers arrive as PDF, scanned PDF, Excel, phone photo or JSON, so the other real work here is
turning each format into something the model can read.

Run:  ./run.sh ladder/step1_one_agent.py data/uc1_supplier_payments/PAY-202611001
      ./run.sh ladder/step1_one_agent.py data/uc1_supplier_payments/PAY-202611008/bank_details_letter.pdf
"""
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

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


# Which form each paper gets, by file name. Order matters: "bundle" before "invoice".
FORMS: list[tuple[str, type[BaseModel]]] = [
    ("bundle", Bundle),
    ("invoice", Invoice),
    ("purchase_order", PurchaseOrder),
    ("services_agreement", ServicesContract),
    ("bank_details_letter", BankDetailsLetter),
]


# ---------------------------------------------------------------------------------------------
# The agent: a model, no tools, and a form to fill. Same recipe for every form.
# ---------------------------------------------------------------------------------------------

model = ChatGoogleGenerativeAI(model=os.environ.get("MODEL_SMALL", "gemini-3.5-flash-lite"))
agents = {}


def agent_for(form: type[BaseModel]):
    if form not in agents:
        agents[form] = create_agent(
            model,
            tools=[],
            system_prompt=(
                "You read the papers behind cross-border supplier payments. Fill the form from the paper. "
                "Copy numbers, references and account numbers exactly. Leave a field empty if it is not printed."
            ),
            response_format=ToolStrategy(form),
        )
    return agents[form]


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


def read_paper(path: str) -> BaseModel | None:
    name = Path(path).name
    if name.endswith(".json"):
        return PaymentInstruction.model_validate_json(Path(path).read_text())
    form = next((form for key, form in FORMS if key in name), None)
    if form is None:
        return None
    result = agent_for(form).invoke({"messages": [HumanMessage(content=read_file(path))]})
    return result["structured_response"]


def papers(path: str) -> list[str]:
    """A file is one paper; a case folder is all of its papers."""
    p = Path(path)
    return [path] if p.is_file() else [str(f) for f in sorted(p.iterdir()) if f.is_file()]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        for path in papers(arg):
            started = time.time()
            paper = read_paper(path)
            if paper is None:
                print(f"{path}   skipped: no form for this kind of paper\n")
                continue
            print(f"{path}   {type(paper).__name__}   ({time.time() - started:.1f} s)")
            print(json.dumps(paper.model_dump(), indent=2, ensure_ascii=False), "\n")
