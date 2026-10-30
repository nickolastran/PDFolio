import difflib
import io
from pathlib import Path

import pikepdf
import pymupdf
from PIL import Image, ImageChops

from app import config, safety
from app.ops.edit import _open, _page, _save, box_rect
from app.tools import UserError


def protect(inputs, opts, out: Path) -> Path:
    """AES-256 (R6). Sanitizes first, since the worker can't open the encrypted result."""
    plain = out / "plain.pdf"
    _open(inputs[0][0]).save(plain, garbage=3, deflate=True)
    safety.sanitize_pdf(plain)
    dest = out / "protected.pdf"
    with pikepdf.open(plain) as pdf:
        pdf.save(dest, encryption=pikepdf.Encryption(user=opts.password, owner=opts.password, R=6))
    plain.unlink()
    return dest


def unlock(inputs, opts, out: Path) -> Path:
    """Remove a password the user knows. One attempt per job; there is no guessing or cracking."""
    try:
        pdf = pikepdf.open(inputs[0][0], password=opts.password)
    except pikepdf.PasswordError:
        raise UserError("Wrong password")
    with pdf:
        if len(pdf.pages) > config.MAX_PAGES:
            raise UserError(f"PDF has more than {config.MAX_PAGES} pages")
        dest = out / "unlocked.pdf"
        pdf.save(dest)
    return dest


def sign(inputs, opts, out: Path) -> Path:
    pdfs = [p for p, k in inputs if k == "pdf"]
    images = [p for p, k in inputs if k != "pdf"]
    if len(pdfs) != 1 or len(images) != 1:
        raise UserError("Add one PDF and one signature image")
    with Image.open(images[0]) as im:
        buf = io.BytesIO()
        im.convert("RGBA").save(buf, "PNG")      # re-encode: drops metadata, normalises format
    doc = _open(pdfs[0])
    for box in opts.places:
        page = _page(doc, box)
        page.insert_image(box_rect(page, box), stream=buf.getvalue(), keep_proportion=True, rotate=page.rotation)
    return _save(doc, out, "signed.pdf")


def redact(inputs, opts, out: Path) -> Path:
    """True redaction: the text, images and drawings under each area are removed, then we check."""
    doc = _open(inputs[0][0])
    areas: dict[int, list[pymupdf.Rect]] = {}
    for box in opts.areas:
        page = _page(doc, box)
        areas.setdefault(box.page, []).append(box_rect(page, box))
    terms = [t for t in (s.strip() for s in opts.terms) if t]
    for page in doc:
        rects = areas.get(page.number, []) + [r for t in terms for r in page.search_for(t)]
        # Notes and comments aren't page content, so redaction alone would leave them behind.
        for annot in list(page.annots()):
            if any(annot.rect.intersects(r) for r in rects) or _mentions(_annot_text(annot), terms):
                page.delete_annot(annot)
        for r in rects:
            page.add_redact_annot(r, fill=(0, 0, 0))
        if rects:
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                                  graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
    # Hidden copies of the text can live in metadata, annotations, form fields and attachments.
    doc.scrub(metadata=True, xml_metadata=True, attached_files=True, embedded_files=True,
              javascript=True, thumbnails=True, reset_fields=True, hidden_text=True,
              redactions=False, remove_links=False)
    dest = _save(doc, out, "redacted.pdf")
    _verify_redaction(dest, terms, areas)
    return dest


def _annot_text(annot) -> str:
    return " ".join(str(v) for v in annot.info.values())


def _mentions(text: str, terms: list[str]) -> bool:
    text = text.lower()
    return any(t.lower() in text for t in terms)


def _verify_redaction(path: Path, terms: list[str], areas: dict[int, list[pymupdf.Rect]]) -> None:
    """Re-open the saved file and look everywhere text can hide: pages, notes, form fields, metadata."""
    doc = pymupdf.open(path)
    found = [p.get_text() for p in doc]
    found += [_annot_text(a) for p in doc for a in p.annots()]
    found += [str(w.field_value) for p in doc for w in p.widgets()]
    found += [str(v) for v in (doc.metadata or {}).values()] + [doc.get_xml_metadata()]
    if _mentions("\n".join(found), terms):
        raise UserError("Redaction could not be verified, so the file was not saved")
    for pno, rects in areas.items():
        for r in rects:
            if doc[pno].get_text(clip=r).strip():
                raise UserError("Redaction could not be verified, so the file was not saved")


def compare(inputs, opts, out: Path) -> Path:
    """A report PDF: each page pair side by side with visual changes boxed, then a text diff."""
    if len(inputs) != 2:
        raise UserError("Add exactly two PDFs")
    a, b = _open(inputs[0][0]), _open(inputs[1][0])
    pages = max(a.page_count, b.page_count)
    if pages > config.MAX_RENDER_PAGES:
        raise UserError(f"Compare is limited to {config.MAX_RENDER_PAGES} pages")
    report = pymupdf.open()
    gap, head = 24, 36
    changed = 0
    for i in range(pages):
        pa = a[i] if i < a.page_count else None
        pb = b[i] if i < b.page_count else None
        w = max(p.rect.width for p in (pa, pb) if p)
        h = max(p.rect.height for p in (pa, pb) if p)
        page = report.new_page(width=2 * w + 3 * gap, height=h + head + gap)
        left = pymupdf.Rect(gap, head, gap + w, head + h)
        right = pymupdf.Rect(2 * gap + w, head, 2 * gap + 2 * w, head + h)
        page.insert_text((gap, 24), f"Page {i + 1}: first file", fontsize=10, fontname="helv")
        page.insert_text((2 * gap + w, 24), f"Page {i + 1}: second file", fontsize=10, fontname="helv")
        for doc, p, rect in ((a, pa, left), (b, pb, right)):
            if p:
                page.show_pdf_page(rect, doc, p.number)
            page.draw_rect(rect, color=(0.6, 0.6, 0.6), width=0.5)
        boxes = _visual_diff(pa, pb)
        changed += bool(boxes)
        for (x0, y0, x1, y1) in boxes:
            for rect in (left, right):
                box = pymupdf.Rect(rect.x0 + x0 * w, rect.y0 + y0 * h, rect.x0 + x1 * w, rect.y0 + y1 * h)
                page.draw_rect(box, color=(0.85, 0.1, 0.1), fill=(1, 0.85, 0.2), fill_opacity=0.25, width=1)
    _text_diff(report, a, b)
    report.insert_page(0, text=f"Compared {a.page_count} and {b.page_count} pages. "
                               f"{changed} page{'s look' if changed != 1 else ' looks'} different.",
                       fontsize=14, fontname="helv")
    return _save(report, out, "comparison.pdf")


def _visual_diff(pa, pb, grid: int = 24) -> list[tuple[float, float, float, float]]:
    """Changed cells of a grid over the page, as 0..1 fractions."""
    if pa is None or pb is None:
        return [(0, 0, 1, 1)]
    ia = Image.frombytes("RGB", *_pix(pa))
    ib = Image.frombytes("RGB", *_pix(pb)).resize(ia.size)
    diff = ImageChops.difference(ia, ib).convert("L").point(lambda v: 255 if v > 40 else 0)
    cw, ch = ia.width / grid, ia.height / grid
    boxes = []
    for gy in range(grid):
        for gx in range(grid):
            if diff.crop((int(gx * cw), int(gy * ch), int((gx + 1) * cw), int((gy + 1) * ch))).getbbox():
                boxes.append((gx / grid, gy / grid, (gx + 1) / grid, (gy + 1) / grid))
    return boxes


def _pix(page):
    pix = page.get_pixmap(dpi=50, alpha=False)
    return (pix.width, pix.height), pix.samples


def _text_diff(report, a, b) -> None:
    lines = list(difflib.unified_diff(
        [ln for p in a for ln in p.get_text().splitlines()],
        [ln for p in b for ln in p.get_text().splitlines()],
        "first file", "second file", lineterm="", n=1))
    if not lines:
        lines = ["The text of both files is the same."]
    per_page = 60
    for start in range(0, len(lines), per_page):
        page = report.new_page()
        page.insert_textbox(pymupdf.Rect(48, 48, 547, 794), "\n".join(lines[start:start + per_page]),
                            fontsize=9, fontname="cour")
