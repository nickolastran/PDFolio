"""Checks against hostile inputs and cleanup of outputs. Runs inside the sandbox."""
import stat
import zipfile
from pathlib import Path, PurePosixPath

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app import config
from app.tools import UserError

ZIP_KINDS = {"docx", "odt", "epub", "pptx", "xlsx", "htmlzip"}
XML_SUFFIXES = (".xml", ".rels", ".opf", ".ncx", ".xhtml", ".svg")


def harden() -> None:
    import warnings
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS
    # Pillow only warns between 1x and 2x the limit; make that a hard stop too.
    warnings.simplefilter("error", Image.DecompressionBombWarning)


def check_input(path: Path, kind: str, encrypted_ok: bool = False) -> None:
    if kind == "pdf":
        check_pdf(path, encrypted_ok)
    elif kind in ZIP_KINDS:
        check_zip(path)
    elif kind in ("jpg", "png"):
        check_image(path)


def check_image(path: Path) -> None:
    from PIL import Image
    try:
        Image.open(path).close()   # reads the header only; harden() makes bombs raise here
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise UserError("Image is too large")
    except Exception:
        raise UserError("This image could not be read")


def check_pdf(path: Path, encrypted_ok: bool = False):
    import pymupdf
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except Exception:
        raise UserError("This PDF could not be read")
    if doc.needs_pass:
        if encrypted_ok:
            return doc   # Unlock checks the page count once the password opens it
        raise UserError("This PDF has a password. Unlock it first.")
    if doc.page_count > config.MAX_PAGES:
        raise UserError(f"PDF has more than {config.MAX_PAGES} pages")
    return doc


def _zip_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = zf.infolist()
    if len(infos) > config.MAX_ZIP_ENTRIES:
        raise UserError("Archive has too many files")
    total = 0
    for i in infos:
        p = PurePosixPath(i.filename.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts:
            raise UserError("Archive contains unsafe paths")
        if stat.S_ISLNK(i.external_attr >> 16):
            raise UserError("Archive contains links")
        if i.file_size > max(i.compress_size, 1) * config.MAX_ZIP_RATIO:
            raise UserError("Archive is too highly compressed")
        total += i.file_size
    if total > config.MAX_UNZIPPED_BYTES:
        raise UserError("Archive is too large when unpacked")
    return infos


def _read_capped(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    # Don't trust the declared size: read at most that many bytes (+1 to detect lies).
    with zf.open(info) as f:
        data = f.read(info.file_size + 1)
    if len(data) > info.file_size:
        raise UserError("Archive is corrupt")
    return data


def check_zip(path: Path) -> None:
    """Zip bomb, zip slip, symlink and XXE checks for any zip-based format."""
    try:
        with zipfile.ZipFile(path) as zf:
            for info in _zip_members(zf):
                if info.filename.lower().endswith(XML_SUFFIXES):
                    try:
                        ElementTree.fromstring(_read_capped(zf, info))
                    except DefusedXmlException:
                        raise UserError("File contains unsafe XML")
                    except ElementTree.ParseError:
                        pass  # malformed XML is the converter's problem, not a security one
    except zipfile.BadZipFile:
        raise UserError("File is corrupt")


def extract_zip(path: Path, dest: Path) -> None:
    with zipfile.ZipFile(path) as zf:
        for info in _zip_members(zf):
            target = dest / info.filename
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_read_capped(zf, info))


# GoToR/GoToE open external or embedded files; MuPDF rewrites Launch links into GoToR.
DANGEROUS_ACTIONS = {"/JavaScript", "/Launch", "/ImportData", "/RichMediaExecute", "/SubmitForm",
                     "/GoToR", "/GoToE"}


def sanitize_pdf(path: Path) -> None:
    """Strip JavaScript, auto-run actions, launch actions and embedded files, in place."""
    import pikepdf
    with pikepdf.open(path, allow_overwriting_input=True) as pdf:
        root = pdf.Root
        for key in ("/OpenAction", "/AA"):
            if key in root:
                del root[key]
        if "/Names" in root:
            for key in ("/JavaScript", "/EmbeddedFiles"):
                if key in root.Names:
                    del root.Names[key]
        if "/AcroForm" in root and "/XFA" in root.AcroForm:
            del root.AcroForm["/XFA"]
        def scrub(obj):
            # Visit direct (inline) children too; indirect ones are covered by pdf.objects.
            if isinstance(obj, pikepdf.Array):
                children = list(obj)
            elif isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)):
                for key in ("/AA", "/JS"):
                    if key in obj:
                        del obj[key]
                if obj.get("/S") in DANGEROUS_ACTIONS:
                    for k in list(obj.keys()):     # empty it, then make it a harmless no-op action
                        del obj[k]
                    obj.S = pikepdf.Name("/Named")
                    obj.N = pikepdf.Name("/None")
                children = [obj[k] for k in obj.keys()]
            else:
                return
            for child in children:
                if isinstance(child, pikepdf.Object) and not child.is_indirect:
                    scrub(child)

        for obj in pdf.objects:
            scrub(obj)
        for page in pdf.pages:
            if "/Annots" in page:
                page.Annots = pdf.make_indirect(pikepdf.Array(
                    a for a in page.Annots if a.get("/Subtype") not in ("/FileAttachment", "/RichMedia")))
        pdf.save(path)
