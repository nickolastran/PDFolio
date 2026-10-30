"""Upload validation: type by content sniffing, sizes, and server-generated file names."""
import re
import uuid
import zipfile
from pathlib import Path

import magic
from fastapi import HTTPException, UploadFile

from app import config

KIND_BY_MIME = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "text/rtf": "rtf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.oasis.opendocument.text": "odt",
    "application/epub+zip": "epub",
}
OOXML_DIRS = {"word/": "docx", "ppt/": "pptx", "xl/": "xlsx"}
ZIP_MIMETYPES = {b"application/vnd.oasis.opendocument.text": "odt", b"application/epub+zip": "epub"}
TEXT_KIND_BY_EXT = {"txt": "txt", "md": "md", "markdown": "md", "html": "html", "htm": "html"}


def _sniff_zip(path: Path) -> str | None:
    """libmagic sometimes reports office files as plain zip; look at the entry names."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if "mimetype" in names and zf.getinfo("mimetype").file_size < 100:
                if kind := ZIP_MIMETYPES.get(zf.read("mimetype").strip()):
                    return kind
            if "[Content_Types].xml" in names:
                for prefix, kind in OOXML_DIRS.items():
                    if any(n.startswith(prefix) for n in names):
                        return kind
            if any(n.lower().endswith((".html", ".htm")) for n in names):
                return "htmlzip"
    except zipfile.BadZipFile:
        pass
    return None


def sniff(path: Path, filename: str) -> str | None:
    """Return the file kind from its content. The extension only picks between text flavours."""
    mime = magic.from_file(str(path), mime=True)
    if mime in KIND_BY_MIME:
        return KIND_BY_MIME[mime]
    if mime in ("application/zip", "application/octet-stream"):
        return _sniff_zip(path)
    if mime.startswith("text/"):
        try:
            path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            return None
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return TEXT_KIND_BY_EXT.get(ext, "html" if mime == "text/html" else "txt")
    return None


def safe_stem(filename: str | None) -> str:
    """Original name, reduced to something harmless for a download name. Never used in paths."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" ._-")[:60] or "file"


async def save(files: list[UploadFile], in_dir: Path) -> list[dict]:
    if not 1 <= len(files) <= config.MAX_FILES:
        raise HTTPException(400, f"Upload between 1 and {config.MAX_FILES} files")
    saved, total = [], 0
    for f in files:
        fid = uuid.uuid4().hex
        dest = in_dir / fid
        size = 0
        with dest.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                total += len(chunk)
                if size > config.MAX_FILE_BYTES:
                    raise HTTPException(413, f"Each file must be under {config.MAX_FILE_BYTES // config.MB} MB")
                if total > config.MAX_TOTAL_BYTES:
                    raise HTTPException(413, f"Files must total under {config.MAX_TOTAL_BYTES // config.MB} MB")
                out.write(chunk)
        kind = sniff(dest, f.filename or "")
        if kind is None:
            raise HTTPException(415, "Unsupported file type")
        saved.append({"id": fid, "kind": kind, "stem": safe_stem(f.filename)})
    return saved
