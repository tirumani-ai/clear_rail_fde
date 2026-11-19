"""Bank detail formats and check digits. Plain code: a misread digit fails a check digit."""
import re

from app.rules.normalize import norm_account


def iban_ok(value: str) -> bool:
    s = norm_account(value)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    moved = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def clabe_ok(value: str) -> bool:
    """Mexico's 18-digit CLABE: the last digit is a weighted check digit (weights 3, 7, 1)."""
    s = norm_account(value)
    if not re.fullmatch(r"\d{18}", s):
        return False
    weights = [3, 7, 1] * 6
    total = sum((int(s[i]) * weights[i]) % 10 for i in range(17))
    return (10 - total % 10) % 10 == int(s[17])


def swift_ok(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?", norm_account(value)))


def ifsc_ok(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", norm_account(value)))


def cnaps_ok(value: str) -> bool:
    return bool(re.fullmatch(r"\d{12}", norm_account(value)))


def account_ok(value: str) -> bool:
    """Any account as printed: an IBAN, a CLABE, or a plain account number."""
    s = norm_account(value)
    if re.match(r"[A-Z]{2}\d{2}", s):
        return iban_ok(s)
    if len(s) == 18 and s.isdigit():
        return clabe_ok(s)
    return bool(re.fullmatch(r"\d{6,20}", s))


def account_of(bank: dict) -> str:
    """The one account identifier a bank record pays into."""
    return norm_account(bank.get("iban") or bank.get("clabe") or bank.get("account_number") or "")


def bank_issues(bank: dict, prefix: str = "") -> list[str]:
    issues = []
    if not swift_ok(bank.get("swift", "")):
        issues.append(f"invalid:{prefix}swift")
    if bank.get("iban") and not iban_ok(bank["iban"]):
        issues.append(f"invalid:{prefix}iban")
    if bank.get("clabe") and not clabe_ok(bank["clabe"]):
        issues.append(f"invalid:{prefix}clabe")
    if bank.get("ifsc") and not ifsc_ok(bank["ifsc"]):
        issues.append(f"invalid:{prefix}ifsc")
    if bank.get("cnaps") and not cnaps_ok(bank["cnaps"]):
        issues.append(f"invalid:{prefix}cnaps")
    if not account_of(bank):
        issues.append(f"missing:{prefix}account")
    return issues
