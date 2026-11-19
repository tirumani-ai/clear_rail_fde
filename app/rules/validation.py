"""Check one paper's form on its own, with plain code. Nothing here compares two papers (that is app/rules/uc1_checks.py).

A failed check means the form cannot be trusted as read: the model misread it, or the paper itself is wrong.
Each issue is a short name: 'missing:<field>', 'invalid:<field>', 'line_<n>_amount', 'lines_dont_add_up'.
"""
import re
from datetime import date
from decimal import Decimal

from app.rules.bank import account_ok, bank_issues, cnaps_ok, ifsc_ok, swift_ok
from app.rules.normalize import money

CENT = Decimal("0.01")


def _date(value) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _required(form: dict, fields: tuple[str, ...]) -> list[str]:
    return [f"missing:{f}" for f in fields if not form.get(f)]


def _currency(form: dict, field: str) -> list[str]:
    return [] if re.fullmatch(r"[A-Z]{3}", str(form.get(field) or "")) else [f"invalid:{field}"]


def _dates(form: dict, fields: tuple[str, ...]) -> list[str]:
    return [f"invalid:{f}" for f in fields if form.get(f) and _date(form[f]) is None]


def _lines(form: dict, total_field: str) -> list[str]:
    """Each line: quantity x unit price = amount. All lines: sum = the total."""
    lines = form.get("lines") or []
    if not lines:
        return ["missing:lines"]
    issues = []
    for n, line in enumerate(lines, start=1):
        if abs(money(Decimal(str(line["quantity"])) * Decimal(str(line["unit_price"]))) - money(line["amount"])) > CENT:
            issues.append(f"line_{n}_amount")
    if abs(sum(money(line["amount"]) for line in lines) - money(form.get(total_field))) > CENT:
        issues.append("lines_dont_add_up")
    return issues


def _invoice(form: dict) -> list[str]:
    issues = _required(form, ("invoice_number", "invoice_date", "seller", "buyer", "invoice_total"))
    issues += _currency(form, "invoice_currency") + _dates(form, ("invoice_date", "due_date")) + _lines(form, "invoice_total")
    issued, due = _date(form.get("invoice_date")), _date(form.get("due_date"))
    if issued and due and due < issued:
        issues.append("due_before_invoice_date")
    if form.get("invoice_bank_account") and not account_ok(form["invoice_bank_account"]):
        issues.append("invalid:invoice_bank_account")
    return issues


def _purchase_order(form: dict) -> list[str]:
    issues = _required(form, ("po_number", "buyer", "supplier", "po_total"))
    return issues + _currency(form, "po_currency") + _dates(form, ("po_date",)) + _lines(form, "po_total")


def _services_contract(form: dict) -> list[str]:
    issues = _required(form, ("contract_number", "provider", "client", "contract_value"))
    return issues + _currency(form, "contract_currency") + _dates(form, ("effective_date",))


def _bank_letter(form: dict) -> list[str]:
    issues = _required(form, ("letter_type", "supplier", "bank_letter_account", "swift"))
    issues += _dates(form, ("letter_date", "effective_date"))
    if form.get("letter_type") and form["letter_type"] not in ("CHANGE", "CONFIRMATION"):
        issues.append("invalid:letter_type")
    if form.get("bank_letter_account") and not account_ok(form["bank_letter_account"]):
        issues.append("invalid:bank_letter_account")
    if form.get("swift") and not swift_ok(form["swift"]):
        issues.append("invalid:swift")
    code, country = form.get("local_code"), form.get("bank_country")
    if code and ((country == "IN" and not ifsc_ok(code)) or (country == "CN" and not cnaps_ok(code))):
        issues.append("invalid:local_code")
    return issues


def _payment_instruction(form: dict) -> list[str]:
    issues = _required(form, ("payment_id", "client_id", "amount", "currency", "purpose_code"))
    if not form.get("invoice_references"):
        issues.append("missing:invoice_references")
    return issues + _currency(form, "currency") + bank_issues(form["beneficiary"]["bank"], "beneficiary_")


CHECKS = {
    "PAYMENT_INSTRUCTION": _payment_instruction,
    "COMMERCIAL_INVOICE": _invoice,
    "PROFORMA_INVOICE": _invoice,
    "PURCHASE_ORDER": _purchase_order,
    "SERVICES_CONTRACT": _services_contract,
    "BANK_DETAILS_LETTER": _bank_letter,
}


def validate(kind: str, form: dict) -> list[str]:
    return CHECKS[kind](form) if kind in CHECKS else []
