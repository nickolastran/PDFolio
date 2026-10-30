import io
from pathlib import Path

import pymupdf
from PIL import Image

from app.tools import UserError

MM = 72 / 25.4
NUMBER_FORMATS = {"n": "{n}", "page_n": "Page {n}", "n_of_total": "{n} of {total}",
                  "page_n_of_total": "Page {n} of {total}"}


def _open(path: Path) -> pymupdf.Document:
    return pymupdf.open(path, filetype="pdf")


def _save(doc: pymupdf.Document, out: Path, name: str) -> Path:
    dest = out / name
    doc.save(dest, garbage=3, deflate=True)
    return dest


def box_rect(page: pymupdf.Page, box) -> pymupdf.Rect:
    """Box in 0..1 fractions of the page as the user sees it -> PyMuPDF (unrotated) coordinates."""
    r = page.rect
    visual = pymupdf.Rect(r.x0 + box.x * r.width, r.y0 + box.y * r.height,
                          r.x0 + (box.x + box.w) * r.width, r.y0 + (box.y + box.h) * r.height)
    return visual * page.derotation_matrix


def _page(doc, box) -> pymupdf.Page:
    if box.page >= doc.page_count:
        raise UserError("A selected area is on a page that doesn't exist")
    return doc[box.page]


def page_numbers(inputs, opts, out: Path) -> Path:
    doc = _open(inputs[0][0])
    vertical, horizontal = opts.position.split("-")
    fmt = NUMBER_FORMATS[opts.format]
    margin = 10 * MM
    total = doc.page_count + opts.start - 1
    for i, page in enumerate(doc):
        r = page.rect
        y0 = r.y1 - margin - opts.size * 1.5 if vertical == "bottom" else r.y0 + margin
        box = pymupdf.Rect(r.x0 + margin, y0, r.x1 - margin, y0 + opts.size * 1.6) * page.derotation_matrix
        align = {"left": 0, "center": 1, "right": 2}[horizontal]
        page.insert_textbox(box, fmt.format(n=i + opts.start, total=total), fontsize=opts.size,
                            fontname="helv", align=align, rotate=page.rotation)
    return _save(doc, out, "numbered.pdf")


def watermark(inputs, opts, out: Path) -> Path:
    pdfs = [p for p, k in inputs if k == "pdf"]
    images = [p for p, k in inputs if k != "pdf"]
    if len(pdfs) != 1:
        raise UserError("Add one PDF")
    if opts.mode == "image" and not images:
        raise UserError("Add an image to use as the watermark")
    doc = _open(pdfs[0])
    stamp = _image_stamp(images[0], opts) if opts.mode == "image" else None
    for page in doc:
        r = page.rect
        if stamp:
            w = r.width * opts.size / 100
            h = w * stamp[1] / stamp[0]
            box = pymupdf.Rect(r.x0 + (r.width - w) / 2, r.y0 + (r.height - h) / 2,
                               r.x0 + (r.width + w) / 2, r.y0 + (r.height + h) / 2)
            page.insert_image(box * page.derotation_matrix, stream=stamp[2], rotate=page.rotation)
        else:
            fontsize = max(r.width, r.height) * opts.size / 100 / max(len(opts.text), 1) * 1.6
            width = pymupdf.get_text_length(opts.text, fontname="helv", fontsize=fontsize)
            center = pymupdf.Point(r.x0 + r.width / 2, r.y0 + r.height / 2)
            start = pymupdf.Point(center.x - width / 2, center.y + fontsize / 3) * page.derotation_matrix
            pivot = center * page.derotation_matrix
            # Rotate around the page centre, on top of whatever rotation the page itself has.
            page.insert_text(start, opts.text, fontsize=fontsize, fontname="helv", color=(0.5, 0.5, 0.5),
                             fill_opacity=opts.opacity / 100, stroke_opacity=opts.opacity / 100,
                             morph=(pivot, pymupdf.Matrix(-opts.rotation - page.rotation)))
    return _save(doc, out, "watermarked.pdf")


def _image_stamp(path: Path, opts) -> tuple[int, int, bytes]:
    """Rotate and fade the image with Pillow, so any angle and opacity work."""
    with Image.open(path) as im:
        im = im.convert("RGBA").rotate(opts.rotation, expand=True, resample=Image.Resampling.BICUBIC)
        alpha = im.getchannel("A").point(lambda a: int(a * opts.opacity / 100))
        im.putalpha(alpha)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return im.width, im.height, buf.getvalue()


def crop(inputs, opts, out: Path) -> Path:
    doc = _open(inputs[0][0])
    for page in doc:
        r = page.rect   # visual: margins are what the user sees as top/right/bottom/left
        visual = pymupdf.Rect(r.x0 + opts.left * MM, r.y0 + opts.top * MM,
                              r.x1 - opts.right * MM, r.y1 - opts.bottom * MM)
        if visual.width < 36 or visual.height < 36:
            raise UserError("Margins are larger than the page")
        new = visual * page.derotation_matrix
        page.set_cropbox(new + (page.cropbox.x0, page.cropbox.y0, page.cropbox.x0, page.cropbox.y0))
    return _save(doc, out, "cropped.pdf")


def annotate(inputs, opts, out: Path) -> Path:
    doc = _open(inputs[0][0])
    for note in opts.notes:
        page = _page(doc, note)
        rect = box_rect(page, note)
        annot = page.add_freetext_annot(rect, note.text, fontsize=note.size, fontname="helv",
                                        text_color=(0, 0, 0), rotate=page.rotation)
        annot.update()
    return _save(doc, out, "annotated.pdf")


def fill_form(inputs, opts, out: Path) -> Path:
    doc = _open(inputs[0][0])
    if not doc.is_form_pdf:
        raise UserError("This PDF has no form fields")
    for page in doc:
        for w in page.widgets():
            if w.field_name not in opts.values:
                continue
            v = opts.values[w.field_name]
            if w.field_type in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                on = w.on_state()
                w.field_value = on if (v is True or v == on) else "Off"
            else:
                w.field_value = str(v)
            w.update()
    return _save(doc, out, "filled.pdf")
