"""Tool registry, shared by the API (validation) and the sandboxed worker (dispatch).

Keep this module light: the API imports it, so no PyMuPDF/pikepdf imports here.
"""
from typing import Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, create_model

from app import config, formats


class UserError(Exception):
    """Raised by ops with a message that is safe to show to the user."""


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Tool(NamedTuple):
    run: str                   # "module.function" in app.ops
    accepts: frozenset[str]    # input kinds, see uploads.KINDS
    options: type[Options] = Options
    min_files: int = 1
    max_files: int = 1
    encrypted_ok: bool = False   # only Unlock takes password-protected PDFs
    sanitize: bool = True        # Protect sanitizes before encrypting, so the worker can't afterwards
    ai: bool = False             # sandbox extracts text, then the API process sends it to Claude


class PageRef(Options):
    file: int = Field(0, ge=0, lt=20)
    page: int = Field(0, ge=0)
    rotate: Literal[0, 90, 180, 270] = 0
    blank: bool = False


class PlanOptions(Options):
    pages: list[PageRef] = Field(min_length=1, max_length=20_000)
    orientation: Literal["keep", "portrait", "landscape"] = "keep"


class SplitOptions(Options):
    mode: Literal["ranges", "every", "each"] = "ranges"
    ranges: str = Field("", max_length=2000)
    every: int = Field(1, ge=1, le=10_000)


class ImageOptions(Options):
    page_size: Literal["fit", "a4", "letter"] = "fit"
    margin: Literal["none", "small", "large"] = "none"


class ConvertOptions(Options):
    to: Literal[tuple(formats.OUTPUTS)]  # type: ignore[valid-type]
    dpi: int = Field(150, ge=36, le=600)


def convert_to(fmt: str) -> type[Options]:
    """Options for a fixed-target converter like "Word to PDF"."""
    return create_model(f"To_{fmt}", __base__=ConvertOptions, to=(Literal[fmt], fmt))


class CompressOptions(Options):
    level: Literal["low", "medium", "high"] = "medium"


class OcrOptions(Options):
    language: Literal["eng"] = "eng"   # add more with tesseract-ocr-<lang> packages
    redo: bool = False


class Box(Options):
    """An area on a page, in 0..1 fractions of the page as displayed (top-left origin)."""
    page: int = Field(ge=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class Note(Box):
    text: str = Field(min_length=1, max_length=2000)
    size: int = Field(12, ge=6, le=72)


class PageNumberOptions(Options):
    position: Literal["bottom-center", "bottom-left", "bottom-right", "top-center", "top-left", "top-right"] = "bottom-center"
    format: Literal["n", "page_n", "n_of_total", "page_n_of_total"] = "n"
    start: int = Field(1, ge=0, le=100_000)
    size: int = Field(10, ge=6, le=36)


class WatermarkOptions(Options):
    mode: Literal["text", "image"] = "text"
    text: str = Field("CONFIDENTIAL", max_length=200)
    opacity: int = Field(30, ge=5, le=100)    # percent
    rotation: int = Field(45, ge=-180, le=180)
    size: int = Field(50, ge=5, le=100)       # percent of page width


class CropOptions(Options):  # millimetres from each edge
    top: float = Field(10, ge=0, le=500)
    right: float = Field(10, ge=0, le=500)
    bottom: float = Field(10, ge=0, le=500)
    left: float = Field(10, ge=0, le=500)


class AnnotateOptions(Options):
    notes: list[Note] = Field(min_length=1, max_length=500)


class FormOptions(Options):
    values: dict[str, str | bool] = Field(max_length=2000)


class PasswordOptions(Options):
    password: str = Field(min_length=1, max_length=128)


class ProtectOptions(Options):
    password: str = Field(min_length=6, max_length=128)


class SignOptions(Options):
    places: list[Box] = Field(min_length=1, max_length=200)


class RedactOptions(Options):
    areas: list[Box] = Field([], max_length=2000)
    terms: list[str] = Field([], max_length=200)


class SummaryOptions(Options):
    length: Literal["short", "medium", "long"] = "medium"


class TranslateOptions(Options):
    language: str = Field(min_length=2, max_length=40, pattern=r"^[^\W\d_][\w ()\-]*$")


PDF = frozenset({"pdf"})
IMAGES = frozenset({"jpg", "png"})
DOCS = frozenset(formats.INPUTS)
CONVERT = "convert.run"

TOOLS: dict[str, Tool] = {
    "merge": Tool("organize.merge", PDF, min_files=2, max_files=20),
    "split": Tool("organize.split", PDF, SplitOptions),
    "remove": Tool("organize.plan", PDF, PlanOptions),
    "extract": Tool("organize.plan", PDF, PlanOptions),
    "rotate": Tool("organize.plan", PDF, PlanOptions),
    "organize": Tool("organize.plan", PDF, PlanOptions, max_files=20),
    "scan": Tool("organize.images", IMAGES, ImageOptions, max_files=20),
    "jpg-to-pdf": Tool("organize.images", IMAGES, ImageOptions, max_files=20),

    "compress": Tool("optimize.compress", PDF, CompressOptions),
    "repair": Tool("optimize.repair", PDF),
    "ocr": Tool("optimize.ocr", PDF, OcrOptions),

    "convert": Tool(CONVERT, DOCS, ConvertOptions),
    "word-to-pdf": Tool(CONVERT, frozenset({"docx", "odt", "rtf"}), convert_to("pdf")),
    "pptx-to-pdf": Tool(CONVERT, frozenset({"pptx"}), convert_to("pdf")),
    "xlsx-to-pdf": Tool(CONVERT, frozenset({"xlsx"}), convert_to("pdf")),
    "html-to-pdf": Tool(CONVERT, frozenset({"html", "htmlzip"}), convert_to("pdf")),
    "pdf-to-jpg": Tool(CONVERT, PDF, convert_to("jpg")),
    "pdf-to-word": Tool(CONVERT, PDF, convert_to("docx")),
    "pdf-to-pptx": Tool(CONVERT, PDF, convert_to("pptx")),
    "pdf-to-xlsx": Tool(CONVERT, PDF, convert_to("xlsx")),
    "pdf-to-pdfa": Tool(CONVERT, PDF, convert_to("pdfa")),
    "pdf-to-md": Tool(CONVERT, PDF, convert_to("md")),

    "page-numbers": Tool("edit.page_numbers", PDF, PageNumberOptions),
    "watermark": Tool("edit.watermark", PDF | IMAGES, WatermarkOptions, max_files=2),
    "crop": Tool("edit.crop", PDF, CropOptions),
    "annotate": Tool("edit.annotate", PDF, AnnotateOptions),
    "fill-form": Tool("edit.fill_form", PDF, FormOptions),

    "protect": Tool("secure.protect", PDF, ProtectOptions, sanitize=False),
    "unlock": Tool("secure.unlock", PDF, PasswordOptions, encrypted_ok=True),
    "sign": Tool("secure.sign", PDF | IMAGES, SignOptions, min_files=2, max_files=2),
    "redact": Tool("secure.redact", PDF, RedactOptions),
    "compare": Tool("secure.compare", PDF, min_files=2, max_files=2),
}

AI_TOOLS: dict[str, Tool] = {
    "summarize": Tool("ai.extract", PDF, SummaryOptions, ai=True),
    "translate": Tool("ai.extract", PDF, TranslateOptions, ai=True),
    "ai-markdown": Tool("ai.extract", PDF, ai=True),
}
if config.AI_ENABLED:
    TOOLS.update(AI_TOOLS)
