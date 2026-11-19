"""Pick the cheapest reader for each file. Plain rules, no model.

  JSON          already a form: read by code
  spreadsheet   each sheet becomes a page of text
  PDF           a page with at least 40 characters of text is read for free; a page with less is a picture
  photo         a picture
Only pictures need a vision model, and only for the pages that are pictures.
"""
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pypdfium2 as pdfium
from PIL import Image
from pypdf import PdfReader

from app.cache import fingerprint

MIN_TEXT = 40
IMAGES = (".png", ".jpg", ".jpeg")


@dataclass
class Document:
    path: str
    fmt: str                         # json, spreadsheet, digital_pdf, scanned_pdf, mixed_pdf, image, unknown
    fingerprint: str
    page_texts: list[str]            # "" for a page that needs vision
    pages_needing_vision: list[int]  # 0-based page numbers
    structured: dict | None = None   # parsed JSON


def read_document(path) -> Document:
    p = Path(path)
    data = p.read_bytes()
    fp, suffix = fingerprint(data), p.suffix.lower()
    if suffix == ".json":
        return Document(str(p), "json", fp, [], [], json.loads(data))
    if suffix in IMAGES:
        return Document(str(p), "image", fp, [""], [0])
    if suffix == ".xlsx":
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, dtype=str)
        return Document(str(p), "spreadsheet", fp, [sheet_text(df) for df in sheets.values()], [])
    if suffix == ".pdf":
        texts = [(page.extract_text() or "").strip() for page in PdfReader(io.BytesIO(data)).pages]
        vision = [i for i, t in enumerate(texts) if len(t) < MIN_TEXT]
        texts = ["" if i in vision else t for i, t in enumerate(texts)]
        fmt = "digital_pdf" if not vision else "scanned_pdf" if len(vision) == len(texts) else "mixed_pdf"
        return Document(str(p), fmt, fp, texts, vision)
    return Document(str(p), "unknown", fp, [], [])


def sheet_text(df: pd.DataFrame) -> str:
    """One row per line, non-empty cells joined by ' | '. Excel dates lose their empty time part."""
    rows = []
    for row in df.fillna("").itertuples(index=False):
        cells = [re.sub(r"^(\d{4}-\d{2}-\d{2}) 00:00:00$", r"\1", str(c).strip()) for c in row if str(c).strip()]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def render_page_png(path: str, page: int) -> bytes:
    p = Path(path)
    if p.suffix.lower() in IMAGES:
        image = Image.open(p).convert("RGB")
    else:
        image = pdfium.PdfDocument(str(p))[page].render(scale=2).to_pil().convert("L")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
