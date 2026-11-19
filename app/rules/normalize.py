"""Make two spellings of the same thing compare equal. Plain code."""
import re
from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher

# Spec, UC1 check 3: compare names "after removing Ltd / Pvt / Co". The long forms go too.
COMPANY_SUFFIXES = {"LTD", "LIMITED", "PVT", "PRIVATE", "CO", "COMPANY", "INC"}


def norm_ref(value) -> str:
    """Invoice, PO and contract numbers: '2006/2026/4245' and '2006 2026 4245' are the same."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def norm_account(value) -> str:
    """Account numbers and IBANs: spaces and dashes are not part of the number."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def norm_name(value) -> str:
    words = re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper()).split()
    return " ".join(w for w in words if w not in COMPANY_SUFFIXES)


def person(value) -> str:
    """'Jonas Petrova, Finance Director' -> 'Jonas Petrova'."""
    return str(value or "").split(",")[0].strip()


def name_score(a, b) -> float:
    a, b = norm_name(a), norm_name(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
