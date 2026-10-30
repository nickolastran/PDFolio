import shutil
from pathlib import Path

import pymupdf

from app.ops.convert import run_tool
from app.tools import UserError

GS_PRESET = {"low": "/printer", "medium": "/ebook", "high": "/screen"}  # 300, 150, 72 dpi images


def compress(inputs, opts, out: Path) -> Path:
    src = inputs[0][0]
    dest = out / "compressed.pdf"
    run_tool(["gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dQUIET", "-sDEVICE=pdfwrite",
              f"-dPDFSETTINGS={GS_PRESET[opts.level]}", "-dCompatibilityLevel=1.7",
              f"-sOutputFile={dest}", str(src)])
    if dest.stat().st_size >= src.stat().st_size:   # already as small as it gets
        shutil.copy(src, dest)
    return dest


def repair(inputs, opts, out: Path) -> Path:
    import pikepdf
    src = inputs[0][0]
    dest = out / "repaired.pdf"
    try:
        with pikepdf.open(src) as pdf:     # qpdf rebuilds broken xref tables and streams
            pdf.save(dest)
    except pikepdf.PdfError:
        try:
            pymupdf.open(src, filetype="pdf").save(dest, garbage=4, clean=True, deflate=True)
        except Exception:
            raise UserError("This PDF is too damaged to repair")
    return dest


def ocr(inputs, opts, out: Path) -> Path:
    import ocrmypdf
    dest = out / "ocr.pdf"
    try:
        ocrmypdf.ocr(inputs[0][0], dest, language=[opts.language], skip_text=not opts.redo,
                     force_ocr=opts.redo, progress_bar=False, jobs=1)
    except ocrmypdf.exceptions.ExitCodeException as e:
        raise UserError("OCR failed") from e
    return dest
