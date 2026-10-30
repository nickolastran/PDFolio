import io
import re
import zipfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from app import config, safety
from app.tools import UserError

A4 = (595, 842)
LETTER = (612, 792)
MARGINS = {"none": 0, "small": 18, "large": 36}


def _open(path: Path) -> pymupdf.Document:
    return pymupdf.open(path, filetype="pdf")


def merge(inputs, opts, out: Path) -> Path:
    doc = pymupdf.open()
    for path, _ in inputs:
        with _open(path) as src:
            doc.insert_pdf(src)
    dest = out / "merged.pdf"
    doc.save(dest, garbage=3, deflate=True)
    return dest


def plan(inputs, opts, out: Path) -> Path:
    """Build a PDF from a page plan. Covers organize, remove, extract and rotate."""
    if len(opts.pages) > config.MAX_PAGES:
        raise UserError(f"Result would have more than {config.MAX_PAGES} pages")
    srcs = [_open(p) for p, _ in inputs]
    doc = pymupdf.open()
    for ref in opts.pages:
        if ref.blank:
            prev = doc[-1].rect if doc.page_count else pymupdf.Rect(0, 0, *A4)
            doc.new_page(width=prev.width, height=prev.height)
        else:
            if ref.file >= len(srcs) or ref.page >= srcs[ref.file].page_count:
                raise UserError("Page selection doesn't match the file")
            doc.insert_pdf(srcs[ref.file], from_page=ref.page, to_page=ref.page)
        page = doc[-1]
        page.set_rotation((page.rotation + ref.rotate) % 360)
    if opts.orientation != "keep":
        doc = _fit_orientation(doc, opts.orientation)
    dest = out / "pages.pdf"
    doc.save(dest, garbage=3, deflate=True)
    return dest


def _fit_orientation(doc: pymupdf.Document, orientation: str) -> pymupdf.Document:
    """Put pages with the wrong shape onto a page of the right shape, scaled to fit."""
    res = pymupdf.open()
    for i, page in enumerate(doc):
        w, h = page.rect.width, page.rect.height   # rect already accounts for rotation
        if (w > h) == (orientation == "landscape") or w == h:
            res.insert_pdf(doc, from_page=i, to_page=i)
        else:
            new = res.new_page(width=h, height=w)
            new.show_pdf_page(new.rect, doc, i, keep_proportion=True)
    return res


RANGE = re.compile(r"^\s*(\d+|end)\s*(?:-\s*(\d+|end)\s*)?$", re.I)


def parse_ranges(text: str, page_count: int) -> list[tuple[int, int]]:
    """'1-3, 4-7, 8-end' -> [(0, 2), (3, 6), (7, n-1)] (0-based, inclusive)."""
    def num(s: str) -> int:
        return page_count if s.lower() == "end" else int(s)

    result = []
    for part in text.split(","):
        if not part.strip():
            continue
        m = RANGE.match(part)
        if not m:
            raise UserError(f"Can't read page range “{part.strip()[:20]}”")
        a = num(m[1])
        b = num(m[2]) if m[2] else a
        if not 1 <= a <= b <= page_count:
            raise UserError(f"Range {part.strip()} is outside pages 1–{page_count}")
        result.append((a - 1, b - 1))
    if not result:
        raise UserError("Enter at least one page range")
    return result


def split(inputs, opts, out: Path) -> Path:
    src = _open(inputs[0][0])
    n = src.page_count
    if opts.mode == "ranges":
        ranges = parse_ranges(opts.ranges, n)
    else:
        step = 1 if opts.mode == "each" else opts.every
        ranges = [(i, min(i + step, n) - 1) for i in range(0, n, step)]
    dest = out / "split.zip"
    tmp = out / "part.pdf"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, (a, b) in enumerate(ranges, 1):
            part = pymupdf.open()
            part.insert_pdf(src, from_page=a, to_page=b)
            part.save(tmp, garbage=3, deflate=True)
            safety.sanitize_pdf(tmp)
            label = f"page-{a + 1}" if a == b else f"pages-{a + 1}-{b + 1}"
            zf.write(tmp, f"{i:03d}-{label}.pdf")
    tmp.unlink()
    return dest


def images(inputs, opts, out: Path) -> Path:
    """Images to one PDF, one image per page. Re-encoding drops EXIF data such as GPS location."""
    doc = pymupdf.open()
    margin = MARGINS[opts.margin]
    for path, kind in inputs:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            buf = io.BytesIO()
            if kind == "jpg":
                im.convert("RGB").save(buf, "JPEG", quality=92)
            else:
                im.save(buf, "PNG")
            w, h = im.size
        if opts.page_size == "fit":
            scale = A4[1] / max(w, h)
            pw, ph = w * scale + 2 * margin, h * scale + 2 * margin
        else:
            pw, ph = A4 if opts.page_size == "a4" else LETTER
            if w > h:
                pw, ph = ph, pw
        page = doc.new_page(width=pw, height=ph)
        page.insert_image(pymupdf.Rect(margin, margin, pw - margin, ph - margin),
                          stream=buf.getvalue(), keep_proportion=True)
    dest = out / "images.pdf"
    doc.save(dest, garbage=3, deflate=True)
    return dest
