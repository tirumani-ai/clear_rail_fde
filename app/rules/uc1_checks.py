"""UC1: the 11 checks from the spec, as plain code. A model never decides any of this.

Each check either passes or names a mismatch code with a sentence saying what it compared. Amounts are exact
decimals. The inputs are the case's papers, how they link (app/rules/linking.py) and master data.
"""
from dataclasses import dataclass
from datetime import date, datetime

from app.ingestion.papers import Paper
from app.master import Master, convert
from app.rules.bank import account_of
from app.rules.injection import find_injection
from app.rules.linking import CaseLinks
from app.rules.normalize import money, name_score, norm_account, norm_ref, person

# Not in the spec: a paper failed its own checks (app/rules/validation.py), so its fields cannot be trusted
# and the case must not clear on them. Ops-level.
UNRELIABLE_READ = "UNRELIABLE_READ"

# Which papers each purpose code needs (master data purpose_codes, spec check 7).
NEEDS = {
    "GDI": "a commercial invoice and a purchase order",
    "ADV": "a proforma invoice",
    "SVC": "an invoice and a services contract",
    "CTR": "an invoice and a contract",
}


@dataclass
class Issue:
    code: str
    message: str


def _date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def paid_before(vendor_id: str, invoice_number: str, currency: str, master: Master):
    """Released payments already made against this invoice, in the invoice's currency."""
    rows = [r for r in master.payment_history
            if r["vendor_id"] == vendor_id and norm_ref(r["invoice_number"]) == norm_ref(invoice_number)
            and r["status"] == "RELEASED"]
    return sum((convert(r["amount"], r["currency"], currency, master) for r in rows), money(0)), rows


def screen(papers: list[Paper], master: Master) -> list[str]:
    """Every party and signatory on every paper, against the watchlist."""
    names: set[str] = set()
    for p in papers:
        f = p.form
        if p.kind == "PAYMENT_INSTRUCTION":
            names |= {f["client_name"], f["beneficiary"]["name"]}
        else:
            for key in ("seller", "buyer", "supplier", "provider", "client", "account_holder", "addressed_to"):
                names.add(f.get(key) or "")
            for key in ("invoice_signatory", "approved_by", "provider_signatory", "client_signatory", "signatory"):
                names.add(person(f.get(key)))
    names.discard("")
    minimum = master.tolerances.get("uc1_screening_match_min", 0.9)
    return sorted({f"{n!r} ~ watchlist {w!r}" for n in names for w in master.watchlist_entities + master.watchlist_people
                   if name_score(n, w) >= minimum})


def run_checks(links: CaseLinks, papers: list[Paper], master: Master) -> list[Issue]:
    issues: list[Issue] = []
    add = lambda code, message: issues.append(Issue(code, message))  # noqa: E731

    unreliable = [f"{p.file.split('/')[-1]} {p.kind}: {p.issues}" for p in papers if p.issues]
    if unreliable:
        add(UNRELIABLE_READ, "papers failed their own checks: " + "; ".join(unreliable))

    for p in papers:  # check 11b: hidden instructions, on the paper's own text
        for line in find_injection(p.text):
            add("SUSPICIOUS_CONTENT", f"{p.file.split('/')[-1]}: {line!r}")

    hits = screen(papers, master)  # check 11a
    if hits:
        add("SCREENING_HIT", "; ".join(hits))

    if links.instruction is None:
        return issues
    pi = links.instruction.form
    paid_bank = pi["beneficiary"]["bank"]
    saved = links.saved_supplier
    if links.invoice is None:
        add("MISSING_SUPPORTING_DOC", "no invoice in the case")
        return issues
    inv = links.invoice.form

    if links.duplicates:  # check 11c
        add("POSSIBLE_DUPLICATE", f"invoice {inv.get('invoice_number')} also uploaded as "
            + ", ".join(p.file.split("/")[-1] for p in links.duplicates))

    # 1. amount <= invoice balance still unpaid (earlier released payments count).
    # 2. currency = invoice currency.
    if pi["currency"] != inv.get("invoice_currency"):
        add("CURRENCY_MISMATCH", f"instruction {pi['currency']}, invoice {inv.get('invoice_currency')}")
    else:
        before, rows = paid_before(pi["beneficiary"]["beneficiary_id"], inv.get("invoice_number"), inv["invoice_currency"], master)
        unpaid = money(inv.get("invoice_total")) - before
        amount = money(pi["amount"])
        if rows and unpaid <= 0:
            add("INVOICE_REUSED", f"invoice {inv.get('invoice_number')} already paid in full ({before:,} by "
                + ", ".join(r["payment_id"] for r in rows) + ")")
        elif amount > unpaid:
            add("AMOUNT_EXCEEDS_INVOICE", f"paying {amount:,} {pi['currency']}, unpaid balance {unpaid:,} "
                f"(total {money(inv.get('invoice_total')):,} less {before:,} paid before)")

    # 3. beneficiary name ~ invoice seller.
    minimum = master.tolerances["uc1_name_match_min"]
    score = name_score(pi["beneficiary"]["name"], inv.get("seller"))
    if score < minimum:
        add("BENEFICIARY_NAME_MISMATCH", f"paying {pi['beneficiary']['name']!r}, invoice seller {inv.get('seller')!r} "
            f"(score {score:.2f} < {minimum})")

    # 4. beneficiary bank country = seller country (the saved supplier's country).
    seller_country = saved["country"] if saved else pi["beneficiary"]["country"]
    if paid_bank["bank_country"] != seller_country:
        add("BENEFICIARY_COUNTRY_MISMATCH", f"bank in {paid_bank['bank_country']}, seller in {seller_country}")

    # 5. bank details = the saved details. Any change goes to a callback, even with a change letter.
    paid_account = account_of(paid_bank)
    saved_account = account_of(saved["bank"]) if saved else ""
    if not saved:
        add("BANK_DETAILS_CHANGED", f"no saved bank details for {pi['beneficiary']['beneficiary_id']}: callback required")
    elif paid_account != saved_account or norm_account(paid_bank["swift"]) != norm_account(saved["bank"]["swift"]):
        letter = next((p for p in links.letters if norm_account(p.form.get("bank_letter_account")) == paid_account), None)
        add("BANK_DETAILS_CHANGED", f"paying {paid_account} / {paid_bank['swift']}, saved {saved_account} / "
            f"{saved['bank']['swift']}" + (f"; a {letter.form.get('letter_type', '').lower()} letter is attached, "
            "callback still required" if letter else "; callback required"))

    # 6. pay-to account printed on the invoice = the account on file.
    on_file = saved_account or paid_account
    printed = norm_account(inv.get("invoice_bank_account"))
    if printed and printed != on_file:
        add("INVOICE_BANK_MISMATCH", f"invoice says pay {printed}, account on file {on_file}")

    # 7. purpose code fits the papers.
    proforma = links.invoice.kind == "PROFORMA_INVOICE"
    fits = {"GDI": links.po is not None and not proforma, "ADV": proforma,
            "SVC": links.contract is not None and not proforma, "CTR": links.contract is not None and not proforma}
    code = pi["purpose_code"]
    if not fits.get(code, False):
        others = [c for c, ok in fits.items() if ok]
        if others:
            add("PURPOSE_CODE_MISMATCH", f"purpose {code} needs {NEEDS.get(code, 'other papers')}; the papers fit {others}")
        else:
            add("MISSING_SUPPORTING_DOC", f"purpose {code} needs {NEEDS.get(code, 'supporting papers')}; "
                + ("; ".join(l.detail for l in links.links if not l.ok) or "none linked to the invoice"))

    # 8. invoice buyer = the client.
    client_name = links.client["legal_name"] if links.client else pi["client_name"]
    score = name_score(inv.get("buyer"), client_name)
    if score < minimum:
        add("BUYER_MISMATCH", f"invoice addressed to {inv.get('buyer')!r}, client is {client_name!r} (score {score:.2f})")

    # 9. invoice total <= PO total.
    if links.po and money(inv.get("invoice_total")) > money(links.po.form.get("po_total")):
        add("PO_MISMATCH", f"invoice {money(inv.get('invoice_total')):,} > PO {money(links.po.form.get('po_total')):,}")

    # 10. invoice no more than 365 days old (on the day the instruction was submitted).
    issued = _date(inv.get("invoice_date"))
    submitted = datetime.fromisoformat(pi["submitted_at"].replace("Z", "+00:00")).date()
    max_age = master.tolerances["uc1_invoice_max_age_days"]
    if issued and (submitted - issued).days > max_age:
        add("STALE_INVOICE", f"invoice dated {issued}, {(submitted - issued).days} days before {submitted} (max {max_age})")

    return issues
