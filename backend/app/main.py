import asyncio
import hashlib
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import ValidationError
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.background import BackgroundTask

from app import config, formats, jobs, uploads
from app.tools import CONVERT, TOOLS


@asynccontextmanager
async def lifespan(app):
    jobs.wipe_data_dir()
    task = asyncio.create_task(jobs.cleanup_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; "
       "font-src 'self'; worker-src 'self' blob:; connect-src 'self'; object-src 'none'; "
       "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
# Multipart framing overhead on top of the file bytes.
MAX_BODY = config.MAX_TOTAL_BYTES + 64 * 1024 * (config.MAX_FILES + 1)


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


@app.middleware("http")
async def security(request: Request, call_next):
    if request.method not in ("GET", "HEAD"):
        # CSRF: the session cookie is SameSite=Strict, and we also require our own Origin.
        if request.headers.get("origin") not in config.ALLOWED_ORIGINS:
            return _error(403, "Forbidden")
        if request.url.path == "/api/jobs":
            cl = request.headers.get("content-length", "")
            if not cl.isdigit():
                return _error(411, "Length required")
            if int(cl) > MAX_BODY:
                return _error(413, f"Files must total under {config.MAX_TOTAL_BYTES // config.MB} MB")

    sid = request.cookies.get("sid")
    new_sid = None
    if not sid or len(sid) != 43:
        sid = new_sid = secrets.token_urlsafe(32)
    request.state.owner = hashlib.sha256(sid.encode()).hexdigest()

    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    if new_sid:
        response.set_cookie("sid", new_sid, httponly=True, secure=config.COOKIE_SECURE,
                            samesite="strict", path="/")
    return response


@app.exception_handler(RequestValidationError)
async def _invalid(request, exc):
    return _error(422, "Invalid request")


@app.exception_handler(RateLimitExceeded)
async def _limited(request, exc):
    return _error(429, "Too many requests. Try again in a minute.")


@app.exception_handler(Exception)
async def _crash(request, exc):
    return _error(500, "Something went wrong")


@app.get("/api/tools")
def list_tools():
    return {
        "tools": {k: {"accepts": sorted(t.accepts), "min_files": t.min_files, "max_files": t.max_files}
                  for k, t in TOOLS.items()},
        "limits": {"file_mb": config.MAX_FILE_BYTES // config.MB,
                   "total_mb": config.MAX_TOTAL_BYTES // config.MB, "files": config.MAX_FILES},
    }


@app.get("/api/formats")
def list_formats():
    return formats.reachable()


@app.post("/api/jobs", status_code=201)
@limiter.limit(config.RATE_LIMIT)
async def create_job(request: Request, tool: str = Form(), options: str = Form("{}"),
                     files: list[UploadFile] = File()):
    t = TOOLS.get(tool)
    if t is None:
        raise HTTPException(404, "Unknown tool")
    try:
        opts = t.options.model_validate_json(options)
    except ValidationError:
        raise HTTPException(422, "Invalid options")
    if not t.min_files <= len(files) <= t.max_files:
        raise HTTPException(400, f"This tool takes {t.min_files} to {t.max_files} files")
    if jobs.active_count() >= config.MAX_QUEUED_JOBS:
        raise HTTPException(503, "Server is busy. Try again shortly.")

    job_id, job = jobs.new_job(request.state.owner, tool)
    try:
        saved = await uploads.save(files, job.dir / "in")
        if any(f["kind"] not in t.accepts for f in saved):
            raise HTTPException(415, "This tool doesn't accept that file type")
        if t.run == CONVERT and formats.path(saved[0]["kind"], opts.to) is None:
            raise HTTPException(415, "This file can't be converted to that format")
    except BaseException:
        jobs.delete(job_id)
        raise
    job.stem = saved[0]["stem"]
    jobs.start(job_id, {"tool": tool, "options": opts.model_dump(mode="json"),
                        "inputs": [{"id": f["id"], "kind": f["kind"]} for f in saved]})
    return {"id": job_id}


def _owned(request: Request, job_id: str) -> jobs.Job:
    job = jobs.get_owned(job_id, request.state.owner)
    if job is None:
        raise HTTPException(404, "Not found")  # same answer for "missing" and "not yours"
    return job


@app.get("/api/jobs/{job_id}")
def job_status(request: Request, job_id: str):
    job = _owned(request, job_id)
    res = {"status": job.status, "error": job.error}
    if job.status == "done" and job.output:
        res["name"] = _default_stem(job)
        res["ext"] = job.output.suffix
    return res


def _default_stem(job: jobs.Job) -> str:
    return job.stem if TOOLS[job.tool].run == CONVERT else f"{job.stem}-{job.tool}"


MEDIA = {
    ".pdf": "application/pdf", ".zip": "application/zip", ".jpg": "image/jpeg", ".png": "image/png",
    ".txt": "text/plain; charset=utf-8", ".md": "text/markdown; charset=utf-8",
    ".html": "text/html; charset=utf-8", ".rtf": "application/rtf", ".epub": "application/epub+zip",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@app.get("/api/jobs/{job_id}/download")
def download(request: Request, job_id: str, delete: bool = False, name: str | None = Query(None, max_length=200)):
    job = _owned(request, job_id)
    if job.status != "done" or job.output is None:
        raise HTTPException(404, "Not found")
    suffix = job.output.suffix
    # A user-chosen name gets the same cleaning as upload names; the extension always comes from the output.
    stem = uploads.safe_stem(name + ".x") if name else _default_stem(job)
    return FileResponse(
        job.output, media_type=MEDIA.get(suffix, "application/octet-stream"),
        filename=stem + suffix,   # FileResponse sends Content-Disposition: attachment
        headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; sandbox"},
        background=BackgroundTask(jobs.delete, job_id) if delete else None)


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(request: Request, job_id: str):
    _owned(request, job_id)
    jobs.delete(job_id)
    return Response(status_code=204)


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    """Built frontend. Only files Vite emitted under assets/ are served; everything else gets the app shell."""
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    assets = (config.FRONTEND_DIST / "assets").resolve()
    f = (config.FRONTEND_DIST / path).resolve()
    if f.is_relative_to(assets) and f.is_file():
        return FileResponse(f, headers={"Cache-Control": "public, max-age=31536000, immutable"})
    index = config.FRONTEND_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(404, "Frontend not built. Run: make build")
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
