"""Find text on a paper that talks to the AI instead of the reader (UC1 code SUSPICIOUS_CONTENT). Plain code.

It reads the paper's own text (the PDF text layer, the spreadsheet cells, or the transcribed scan), never the
model's filled form, so a model that was fooled cannot hide what fooled it.
"""
import re

PATTERNS = [
    r"\bignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|rules)",
    r"\b(note|message|instruction)s? to (the )?(ai|model|assistant|system|llm)\b",
    r"\b(ai|llm) (system|model|assistant)\b",
    r"\bmark (all|every) (checks?|tests?) as (passed|ok|clear)",
    r"\b(approve|release) (this|the) payment (immediately|now|without)",
    r"\bdisregard (the|all|any) (checks?|rules|instructions)",
    r"\byou are (now )?(an?|the) (ai|assistant|model)\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in PATTERNS]


def find_injection(text: str) -> list[str]:
    """The lines that look like instructions to an AI, if any."""
    return [line.strip() for line in text.splitlines() if any(p.search(line) for p in _COMPILED)]
