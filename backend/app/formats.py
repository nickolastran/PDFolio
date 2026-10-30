"""Conversion graph: which format can become which, and through which converter.

Pure data so the API can compute reachable formats without importing any converters.
"""
from collections import deque

# Output file extension per format ("pdfa" is a PDF; "htmlzip" is input only).
EXT = {"pdf": "pdf", "pdfa": "pdf", "docx": "docx", "odt": "odt", "rtf": "rtf", "txt": "txt",
       "md": "md", "html": "html", "epub": "epub", "jpg": "jpg", "png": "png", "pptx": "pptx",
       "xlsx": "xlsx"}

_PANDOC_IN = ("md", "html", "docx", "odt", "epub")
# Pandoc writes only formats that need no data files: the Ubuntu build can't load them under --sandbox.
# LibreOffice writes docx/odt/epub instead.
_PANDOC_OUT = ("md", "html", "rtf", "txt")
_LO = (("docx", "odt"), ("odt", "docx"), ("rtf", "docx"), ("rtf", "odt"), ("html", "docx"), ("html", "odt"),
       ("docx", "epub"), ("odt", "epub"))

# (from, to) -> converter function name in app.ops.convert. Order matters: BFS tries earlier edges first.
EDGES: dict[tuple[str, str], str] = {
    **{(s, "pdf"): "libreoffice" for s in ("docx", "odt", "rtf", "pptx", "xlsx")},
    ("html", "pdf"): "weasyprint",
    ("htmlzip", "pdf"): "weasyprint_zip",
    ("htmlzip", "html"): "zip_main_html",
    **{edge: "libreoffice" for edge in _LO},
    **{(s, d): "pandoc" for s in _PANDOC_IN for d in _PANDOC_OUT if s != d},
    ("txt", "html"): "text_to_html",
    ("txt", "md"): "copy",
    ("pdf", "docx"): "pdf_to_docx",
    ("pdf", "pptx"): "pdf_to_pptx",
    ("pdf", "xlsx"): "pdf_to_xlsx",
    ("pdf", "md"): "pdf_to_md",
    ("pdf", "txt"): "pdf_to_txt",
    ("pdf", "pdfa"): "pdf_to_pdfa",
    ("pdf", "jpg"): "pdf_to_image",
    ("pdf", "png"): "pdf_to_image",
    ("jpg", "pdf"): "image_to_pdf",
    ("png", "pdf"): "image_to_pdf",
    ("jpg", "png"): "image_to_image",
    ("png", "jpg"): "image_to_image",
}
MAX_STEPS = 3
# Only meaningful on a real PDF: "Markdown to Excel via PDF tables" is not a conversion anyone wants.
FIRST_STEP_ONLY = {("pdf", "pptx"), ("pdf", "xlsx")}


def path(src: str, dst: str) -> list[tuple[str, str]] | None:
    """Shortest list of edges from src to dst, or None if there is none within MAX_STEPS."""
    if src == dst:
        return None
    prev: dict[str, str] = {src: ""}
    queue = deque([(src, 0)])
    while queue:
        node, depth = queue.popleft()
        if node == dst:
            steps = []
            while node != src:
                steps.append((prev[node], node))
                node = prev[node]
            return steps[::-1]
        if depth == MAX_STEPS:
            continue
        for a, b in EDGES:
            if a == node and b not in prev and (depth == 0 or (a, b) not in FIRST_STEP_ONLY):
                prev[b] = node
                queue.append((b, depth + 1))
    return None


INPUTS = sorted({a for a, _ in EDGES})
OUTPUTS = sorted({b for _, b in EDGES})


def reachable() -> dict[str, list[str]]:
    return {s: [d for d in OUTPUTS if path(s, d)] for s in INPUTS}


if __name__ == "__main__":
    assert path("md", "pdf") == [("md", "html"), ("html", "pdf")]
    assert path("md", "epub") == [("md", "html"), ("html", "docx"), ("docx", "epub")]
    assert path("docx", "pdf") == [("docx", "pdf")]
    assert path("pdf", "odt") == [("pdf", "docx"), ("docx", "odt")]
    assert path("jpg", "pdfa") == [("jpg", "pdf"), ("pdf", "pdfa")]
    assert path("pdfa", "pdf") is None and path("pdf", "htmlzip") is None
    assert path("md", "xlsx") is None and path("pdf", "xlsx") == [("pdf", "xlsx")]
    print(reachable())
