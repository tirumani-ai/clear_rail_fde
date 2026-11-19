"""Which papers in a case belong to the payment, linked by STRONG keys. Plain code, no model.

A UC1 case already arrives as one folder, so this is not grouping loose files. It answers: which invoice is
being paid (the instruction quotes its number), which PO or contract that invoice points to, and which
saved supplier and client the payment names. A paper that should link but does not is reported, not guessed.

STRONG keys (an exact match after normalising links two papers):
  inv:<number>  the instruction's invoice_references and the invoice's own number
  ref:<number>  the invoice's reference ('Your Ref') and a purchase order's or a services contract's number.
                The invoice prints one reference; which kind of paper carries that number says what it is.
  vendor:<id>   the instruction's beneficiary_id and the saved supplier in master data
  client:<id>   the instruction's client_id and the client in master data
WEAK keys (names, bank names) are shown as hints and never used to link: two suppliers can share a bank,
and a supplier's name is spelt many ways. Whether a name is close enough is a CHECK (uc1_checks.py), not a link.
"""
from dataclasses import dataclass, field

from app.ingestion.papers import Paper
from app.master import Master
from app.rules.normalize import norm_ref
from app.schemas import INVOICE_KINDS


@dataclass
class Link:
    name: str
    ok: bool
    detail: str


@dataclass
class CaseLinks:
    case_id: str
    instruction: Paper | None = None
    invoice: Paper | None = None              # the invoice being paid
    duplicates: list[Paper] = field(default_factory=list)  # the same invoice again, as another file
    other_invoices: list[Paper] = field(default_factory=list)
    po: Paper | None = None
    contract: Paper | None = None
    letters: list[Paper] = field(default_factory=list)
    saved_supplier: dict | None = None
    client: dict | None = None
    links: list[Link] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)


def strong_keys(paper: Paper) -> set[str]:
    f, keys = paper.form, set()
    if paper.kind == "PAYMENT_INSTRUCTION":
        keys |= {f"inv:{norm_ref(r)}" for r in f["invoice_references"]}
        keys |= {f"vendor:{f['beneficiary']['beneficiary_id']}", f"client:{f['client_id']}"}
    elif paper.kind in INVOICE_KINDS:
        keys |= {f"inv:{norm_ref(f.get('invoice_number'))}"}
        keys |= {f"ref:{norm_ref(f['reference'])}"} if f.get("reference") else set()
    elif paper.kind == "PURCHASE_ORDER" and f.get("po_number"):
        keys.add(f"ref:{norm_ref(f['po_number'])}")
    elif paper.kind == "SERVICES_CONTRACT" and f.get("contract_number"):
        keys.add(f"ref:{norm_ref(f['contract_number'])}")
    return keys


def _first_with(papers: list[Paper], key: str) -> Paper | None:
    return next((p for p in papers if key in strong_keys(p)), None)


def link_case(case_id: str, papers: list[Paper], master: Master) -> CaseLinks:
    out = CaseLinks(case_id)
    out.instruction = next((p for p in papers if p.kind == "PAYMENT_INSTRUCTION"), None)
    invoices = [p for p in papers if p.kind in INVOICE_KINDS]
    pos = [p for p in papers if p.kind == "PURCHASE_ORDER"]
    contracts = [p for p in papers if p.kind == "SERVICES_CONTRACT"]
    out.letters = [p for p in papers if p.kind == "BANK_DETAILS_LETTER"]
    if out.instruction is None:
        out.links.append(Link("instruction", False, "no payment instruction in the case"))
        return out
    pi = out.instruction.form

    # The invoice being paid: the one whose number the instruction quotes.
    refs = sorted(k for k in strong_keys(out.instruction) if k.startswith("inv:"))
    out.invoice = next((p for p in invoices if strong_keys(p) & set(refs)), None)
    if out.invoice:
        out.links.append(Link("instruction -> invoice", True, f"{refs[0]}"))
    else:
        out.invoice = invoices[0] if invoices else None
        out.links.append(Link("instruction -> invoice", False,
                              f"instruction quotes {pi['invoice_references']}, "
                              + (f"invoice says {out.invoice.form.get('invoice_number')!r}" if out.invoice else "no invoice in the case")))

    if out.invoice:
        number = f"inv:{norm_ref(out.invoice.form.get('invoice_number'))}"
        for p in invoices:
            if p is not out.invoice:
                (out.duplicates if number in strong_keys(p) else out.other_invoices).append(p)
        inv = out.invoice.form
        if inv.get("reference"):
            ref = f"ref:{norm_ref(inv['reference'])}"
            out.po, out.contract = _first_with(pos, ref), _first_with(contracts, ref)
            found = out.po or out.contract
            in_case = [p.form.get("po_number") or p.form.get("contract_number") for p in pos + contracts]
            out.links.append(Link("invoice -> PO or contract", found is not None,
                                  f"{ref} -> {found.kind if found else 'no paper in the case carries it'}"
                                  + (f" (the case has {in_case})" if in_case and not found else "")))
        else:
            out.links.append(Link("invoice -> PO or contract", False, "the invoice prints no reference"))

    vendor = pi["beneficiary"]["beneficiary_id"]
    out.saved_supplier = master.beneficiaries.get(vendor)
    out.links.append(Link("beneficiary -> saved supplier", out.saved_supplier is not None, f"vendor:{vendor}"))
    out.client = master.clients.get(pi["client_id"])
    out.links.append(Link("client -> client on file", out.client is not None, f"client:{pi['client_id']}"))

    # Weak keys: hints only.
    names = {pi["beneficiary"]["name"]} | {p.form.get("seller", "") for p in invoices} | {p.form.get("supplier", "") for p in pos + out.letters}
    names.discard("")
    if len(names) > 1:
        out.hints.append(f"supplier written as {sorted(names)}")
    unlinked = [p for p in pos if p is not out.po] + [p for p in contracts if p is not out.contract]
    for p in unlinked:
        out.hints.append(f"{p.kind} in {p.file.split('/')[-1]} links to nothing")
    return out
