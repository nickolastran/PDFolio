from pathlib import Path

import pymupdf

from app import config
from app.tools import UserError


def extract(inputs, opts, out: Path) -> Path:
    """Sandbox half of the AI tools: PDF to plain text. The API process sends only this text on."""
    text = "\n\n".join(p.get_text() for p in pymupdf.open(inputs[0][0], filetype="pdf")).strip()
    if not text:
        raise UserError("No text found. Run OCR on scanned PDFs first.")
    if len(text) > config.AI_MAX_CHARS:
        raise UserError("This PDF has too much text for the AI tools")
    dest = out / "text.txt"
    dest.write_text(text)
    return dest
