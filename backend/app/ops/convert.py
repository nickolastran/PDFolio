"""Format conversion along the graph in app.formats. Runs inside the sandbox."""
import html
import os
import shutil
import signal
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import pymupdf
from PIL import Image, ImageOps
from weasyprint import HTML, URLFetcher

from app import config, formats, safety
from app.tools import ImageOptions, UserError

TOOL_TIMEOUT = max(config.JOB_TIMEOUT_SECONDS - 10, 10)

# Fresh LibreOffice profile per job with macros disabled outright.
LO_PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop></item>
</oor:items>
"""


def run_tool(argv: list[str], cwd: Path | None = None) -> None:
    """Run an external program: argument list (never a shell), own process group, hard timeout."""
    out = None if config.DEBUG_JOBS else subprocess.DEVNULL
    proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                            start_new_session=True)
    try:
        code = proc.wait(TOOL_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        raise UserError("Took too long to process")
    if code != 0:
        raise UserError("Conversion failed")


def run(inputs, opts, out: Path) -> Path:
    src, kind = inputs[0]
    steps = formats.path(kind, opts.to)
    if steps is None:
        raise UserError("This file can't be converted to that format")
    current = src
    for i, (a, b) in enumerate(steps):
        work = out.parent / "work" / str(i)   # removed by the API when the job ends
        work.mkdir(parents=True)
        current = CONVERTERS[formats.EDGES[(a, b)]](current, a, b, work, opts)
    ext = current.suffix if current.suffix == ".zip" else "." + formats.EXT[opts.to]
    dest = out / f"converted{ext}"
    shutil.move(current, dest)
    return dest


# --- converters: (src, from, to, workdir, opts) -> output path ----------------------

def libreoffice(src, a, b, work, opts):
    profile = work / "profile" / "user"
    profile.mkdir(parents=True)
    (profile / "registrymodifications.xcu").write_text(LO_PROFILE)
    inp = work / f"input.{a}"                       # LibreOffice picks its import filter by extension
    shutil.copy(src, inp)
    target = {"pdf": "pdf", "odt": "odt", "docx": "docx:MS Word 2007 XML", "epub": "epub"}[b]
    argv = ["soffice", f"-env:UserInstallation={profile.parent.as_uri()}", "--headless",
            "--norestore", "--nolockcheck", "--convert-to", target, "--outdir", str(work / "out")]
    if a == "html":
        argv.append("--infilter=HTML (StarWriter)")   # open as a Writer document, not Writer/Web
    run_tool(argv + [str(inp)])
    dest = work / "out" / f"input.{formats.EXT[b]}"
    if not dest.is_file():
        raise UserError("Conversion failed")
    return dest


PANDOC_IN = {"md": "markdown", "html": "html", "docx": "docx", "odt": "odt", "epub": "epub"}
PANDOC_OUT = {"md": "gfm", "html": "html", "rtf": "rtf", "txt": "plain"}


def pandoc(src, a, b, work, opts):
    # No --embed-resources: in pandoc 3.1 it reads local files even under --sandbox (see tests).
    dest = work / f"out.{formats.EXT[b]}"
    argv = ["pandoc", "--sandbox", "-f", PANDOC_IN[a], "-t", PANDOC_OUT[b], "-o", str(dest)]
    if b in ("html", "rtf"):
        argv += ["--standalone", "--metadata", "title=Document"]
    run_tool(argv + [str(src)])
    return dest


class SafeFetcher(URLFetcher):
    """WeasyPrint URL fetcher: data: URIs, plus files inside `root` (the unpacked zip). Nothing else.

    Blocks http(s), file:// outside the upload, localhost, internal IPs and cloud metadata endpoints.
    """

    def __init__(self, root: Path | None):
        super().__init__(allowed_protocols={"data", "file"}, allow_redirects=False)
        self.root = root.resolve() if root else None

    def fetch(self, url, headers=None):
        if url.startswith("data:"):
            return super().fetch(url, headers)
        if self.root and url.startswith("file:"):
            p = Path(urllib.request.url2pathname(urlparse(url).path))
            if not p.is_symlink() and p.resolve().is_relative_to(self.root) and p.is_file():
                return super().fetch(p.resolve().as_uri(), headers)
        raise ValueError("External resources are not allowed")


def _weasy(main: Path, root: Path | None, dest: Path) -> Path:
    base = root.as_uri() + "/" if root else None
    HTML(string=main.read_bytes().decode("utf-8", "replace"), base_url=base,
         url_fetcher=SafeFetcher(root)).write_pdf(dest)
    return dest


def weasyprint(src, a, b, work, opts):
    return _weasy(src, None, work / "out.pdf")


def _unzip_site(src, work) -> tuple[Path, Path]:
    root = work / "site"
    safety.extract_zip(src, root)
    pages = sorted((p for p in root.rglob("*") if p.suffix.lower() in (".html", ".htm")),
                   key=lambda p: (p.name.lower() not in ("index.html", "index.htm"), len(p.parts)))
    if not pages:
        raise UserError("No HTML file found in the zip")
    return pages[0], root


def weasyprint_zip(src, a, b, work, opts):
    main, root = _unzip_site(src, work)
    return _weasy(main, root, work / "out.pdf")


def zip_main_html(src, a, b, work, opts):
    main, _ = _unzip_site(src, work)
    return main


def text_to_html(src, a, b, work, opts):
    text = html.escape(src.read_bytes().decode("utf-8", "replace"))
    dest = work / "out.html"
    dest.write_text('<!doctype html><meta charset="utf-8"><title>Document</title>'
                    '<pre style="white-space:pre-wrap;font:11pt/1.5 monospace">' + text + "</pre>")
    return dest


def copy(src, a, b, work, opts):
    dest = work / f"out.{formats.EXT[b]}"
    shutil.copy(src, dest)
    return dest


def pdf_to_docx(src, a, b, work, opts):
    from pdf2docx import Converter
    dest = work / "out.docx"
    cv = Converter(str(src))
    try:
        cv.convert(str(dest))
    finally:
        cv.close()
    return dest


def _render(src, dpi: int, max_pages: int):
    """Yield (index, pixmap), capping DPI, page count and pixels per page."""
    dpi = min(dpi, config.MAX_RENDER_DPI)
    doc = pymupdf.open(src, filetype="pdf")
    if doc.page_count > max_pages:
        raise UserError(f"Rendering is limited to {max_pages} pages")
    for i, page in enumerate(doc):
        scale = dpi / 72
        w, h = page.rect.width * scale, page.rect.height * scale
        if w * h > config.MAX_IMAGE_PIXELS:
            scale *= (config.MAX_IMAGE_PIXELS / (w * h)) ** 0.5
        yield i, page.get_pixmap(matrix=pymupdf.Matrix(scale, scale)), page


def pdf_to_image(src, a, b, work, opts):
    files = []
    for i, pix, _ in _render(src, opts.dpi, config.MAX_RENDER_PAGES):
        p = work / f"page-{i + 1:03d}.{b}"
        if b == "jpg":
            pix.save(p, jpg_quality=90)
        else:
            pix.save(p)
        files.append(p)
    if len(files) == 1:
        return files[0]
    dest = work / "pages.zip"
    with zipfile.ZipFile(dest, "w") as zf:
        for p in files:
            zf.write(p, p.name)
    return dest


def pdf_to_pptx(src, a, b, work, opts):
    from pptx import Presentation
    from pptx.util import Emu
    prs = Presentation()
    for i, pix, page in _render(src, 150, config.MAX_RENDER_PAGES):
        if i == 0:
            prs.slide_width, prs.slide_height = Emu(int(page.rect.width * 12700)), Emu(int(page.rect.height * 12700))
        img = work / f"{i}.png"
        pix.save(img)
        slide = prs.slides.add_slide(prs.slide_layouts[6])   # blank layout
        slide.shapes.add_picture(str(img), 0, 0, prs.slide_width, prs.slide_height)
    dest = work / "out.pptx"
    prs.save(dest)
    return dest


def pdf_to_xlsx(src, a, b, work, opts):
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    for pno, page in enumerate(pymupdf.open(src, filetype="pdf")):
        for k, table in enumerate(page.find_tables().tables, 1):
            ws = wb.create_sheet(f"Page {pno + 1} table {k}"[:31])
            for r, row in enumerate(table.extract(), 1):
                for c, value in enumerate(row, 1):
                    cell = ws.cell(r, c, value or "")
                    cell.data_type = "s"   # never a formula: blocks "=HYPERLINK(...)" style injection
    if not wb.worksheets:
        raise UserError("No tables found in this PDF")
    dest = work / "out.xlsx"
    wb.save(dest)
    return dest


def pdf_to_md(src, a, b, work, opts):
    import pymupdf4llm
    dest = work / "out.md"
    dest.write_text(pymupdf4llm.to_markdown(pymupdf.open(src, filetype="pdf")))
    return dest


def pdf_to_txt(src, a, b, work, opts):
    dest = work / "out.txt"
    dest.write_text("\n\f".join(p.get_text() for p in pymupdf.open(src, filetype="pdf")))
    return dest


def pdf_to_pdfa(src, a, b, work, opts):
    import ocrmypdf
    dest = work / "out.pdf"
    # tesseract_timeout=0 means "don't OCR": ocrmypdf is used here only for its PDF/A conversion.
    ocrmypdf.ocr(src, dest, output_type="pdfa-2", skip_text=True, tesseract_timeout=0,
                 progress_bar=False, jobs=1)
    return dest


def image_to_pdf(src, a, b, work, opts):
    from app.ops.organize import images
    return images([(src, a)], ImageOptions(), work)


def image_to_image(src, a, b, work, opts):
    dest = work / f"out.{b}"
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if b == "jpg":
            im.convert("RGB").save(dest, "JPEG", quality=92)
        else:
            im.save(dest, "PNG")
    return dest


CONVERTERS = {name: globals()[name] for name in set(formats.EDGES.values())}
