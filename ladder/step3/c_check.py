"""STEP 3c: fill one form per paper, then check each form with code.

For each paper the model fills the matching form (app/schemas.py) from the paper's TEXT. Scans were already
copied into text in 3b, so no picture is sent again. The answer is saved, so a second run is free and identical.
The payment instruction needs no model at all. Then plain code checks every form on its own
(app/rules/validation.py): required fields, valid dates, a due date after the invoice date, each line's
quantity x price, the lines adding up to the total, and the check digits of IBANs, CLABEs, SWIFT, IFSC and CNAPS codes.

Run:  ./run.sh ladder/step3/c_check.py                (all 32 cases; first run: one model call per paper)
      ./run.sh ladder/step3/c_check.py --misread      (pretend every invoice total was read 1,000 too high: the checks catch it)
      ./run.sh ladder/step3/c_check.py --bad-ref      (pretend every PO number on an invoice was misread: no check here sees it)
"""
import collections

from common import answer_key, case_dirs, flags, pretend

from app.ingestion.papers import read_case
from app.rules.normalize import money, norm_account, person

# Fields in the answer key and the paper they are read from.
FIELDS = {
    "invoice": ["invoice_number", "invoice_date", "due_date", "seller", "buyer",
                "invoice_total", "invoice_currency", "invoice_bank_account", "invoice_signatory"],
    "PURCHASE_ORDER": ["po_number", "po_total"],
    "SERVICES_CONTRACT": ["contract_number"],
    "BANK_DETAILS_LETTER": ["bank_letter_account"],
}


def same(field: str, got, want) -> bool:
    if want in (None, ""):
        return got in (None, "", 0)
    if isinstance(want, (int, float)):
        return money(got) == money(want)
    if "account" in field:
        return norm_account(got) == norm_account(want)
    if "signatory" in field:
        return person(got).casefold() == str(want).casefold()
    return str(got).strip().casefold() == str(want).strip().casefold()


def line(p) -> str:
    f = p.form
    return {
        "PAYMENT_INSTRUCTION": f"pay {f.get('amount')} {f.get('currency')} to {f.get('beneficiary', {}).get('name')}",
        "COMMERCIAL_INVOICE": f"invoice {f.get('invoice_number')}  ref {f.get('reference')}  total {f.get('invoice_total')} {f.get('invoice_currency')}",
        "PROFORMA_INVOICE": f"proforma {f.get('invoice_number')}  ref {f.get('reference')}  total {f.get('invoice_total')} {f.get('invoice_currency')}",
        "PURCHASE_ORDER": f"PO {f.get('po_number')}  total {f.get('po_total')} {f.get('po_currency')}",
        "SERVICES_CONTRACT": f"contract {f.get('contract_number')}  value {f.get('contract_value')}",
        "BANK_DETAILS_LETTER": f"{(f.get('letter_type') or '').lower()} letter  account {f.get('bank_letter_account')}",
    }.get(p.kind, p.kind)


def main():
    key, fields, by = answer_key(), collections.Counter(), collections.Counter()
    flagged, wrong_fields = 0, []
    for case in case_dirs():
        papers = pretend(read_case(case), flags())
        for p in papers:
            by[p.by] += 1
            flagged += bool(p.issues)
            name = p.file.split("/")[-1]
            print(f"{case.name}/{name:28} {p.by:5} {line(p):58} checks: {p.issues or 'ok'}")
        # Score the fields against the answer key (the first invoice in the case is the one paid in UC1's data).
        expected = key[case.name]["expected_fields"]
        first = {"invoice": next((p for p in papers if p.kind.endswith("_INVOICE")), None)}
        first |= {k: next((p for p in papers if p.kind == k), None) for k in FIELDS if k != "invoice"}
        for kind, names in FIELDS.items():
            for f in names:
                if f not in expected or (first[kind] is None and expected[f] in (None, "")):
                    continue
                got = first[kind].form.get(f) if first[kind] else None
                ok = same(f, got, expected[f])
                fields["right" if ok else "wrong"] += 1
                if not ok:
                    wrong_fields.append(f"{case.name} {f}: read {got!r}, answer key {expected[f]!r}")
    total = fields["right"] + fields["wrong"]
    print(f"\nPapers: {sum(by.values())} (filled by code {by['code']}, model {by['model']}, saved {by['saved']}). "
          f"Papers failing their own checks: {flagged}.")
    print(f"Fields that match the answer key: {fields['right']}/{total}.")
    for w in wrong_fields:
        print("  -", w)


if __name__ == "__main__":
    main()
