"""Where one paper ends and the next begins. Plain rules, no model.

A page whose first lines carry a title code knows (COMMERCIAL INVOICE, PURCHASE ORDER, ...) starts a new paper.
A page with no title continues the paper before it. A first page with no title gets kind None, and only then
is the classifier model asked (app/ingestion/papers.py).
"""
import re
from dataclasses import dataclass

HEAD_LINES = 6  # titles are looked for in the first six lines of a page

# Checked in this order for each line; the first line that holds a title wins.
TITLES: list[tuple[str, tuple[str, ...]]] = [
    ("PROFORMA_INVOICE", ("PROFORMA INVOICE", "PRO FORMA INVOICE")),
    ("BANK_DETAILS_LETTER", ("BANK DETAILS", "BANK ACCOUNT DETAILS")),
    ("SERVICES_CONTRACT", ("SERVICES AGREEMENT", "SERVICE AGREEMENT", "SERVICES CONTRACT")),
    ("PURCHASE_ORDER", ("PURCHASE ORDER",)),
    ("COMMERCIAL_INVOICE", ("COMMERCIAL INVOICE", "TAX INVOICE")),
]
EXACT = {"INVOICE": "COMMERCIAL_INVOICE"}  # a line that is only this word ("Invoice No:" is not a title)


@dataclass
class Part:
    kind: str | None
    start: int  # 1-based, inclusive
    end: int


def _clean(line: str) -> str:
    """Upper case, punctuation and markdown (**, #, |) removed, spaces squeezed."""
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", line.upper()).split())


def title_kind(text: str) -> str | None:
    """The kind of paper this page starts, or None if it carries no title we know."""
    head = [c for c in (_clean(line) for line in text.splitlines()) if c][:HEAD_LINES]
    for line in head:
        if line in EXACT:
            return EXACT[line]
        for kind, phrases in TITLES:
            if any(phrase in line for phrase in phrases):
                return kind
    return None


def split_papers(pages: list[str], use_titles: bool = True) -> list[Part]:
    parts: list[Part] = []
    for number, text in enumerate(pages, start=1):
        kind = title_kind(text) if use_titles else None
        if kind or not parts:
            parts.append(Part(kind, number, number))
        else:
            parts[-1].end = number
    return parts
