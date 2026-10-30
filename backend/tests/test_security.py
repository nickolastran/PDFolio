"""Security tests with crafted hostile inputs. Files are built here, not committed as blobs."""
import asyncio
import io
import json
import stat
import time
import zipfile
from pathlib import Path

import pikepdf
import pytest
from PIL import Image

from app import config, jobs, safety, sandbox
from app.tools import UserError
from conftest import ORIGIN, make_pdf, run_job

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


# --- upload validation ------------------------------------------------------

def test_wrong_extension_is_rejected(client):
    r = client.post("/api/jobs", data={"tool": "merge"},
                    files=[("files", ("a.pdf", PNG)), ("files", ("b.pdf", make_pdf("x")))])
    assert r.status_code == 415


def test_pdf_named_txt_is_still_a_pdf(client):
    job = run_job(client, "merge", [("a.txt", make_pdf("A")), ("b.exe", make_pdf("B"))])
    assert client.get(f"/api/jobs/{job}/download").content.startswith(b"%PDF")


def test_path_traversal_filename(client):
    job = run_job(client, "merge", [("../../../../etc/passwd.pdf", make_pdf("A")),
                                    ("..\\..\\win.ini", make_pdf("B"))])
    r = client.get(f"/api/jobs/{job}/download")
    assert r.headers["content-disposition"] == 'attachment; filename="passwd-merge.pdf"'
    # Uploads were stored under random names (and deleted after the job); nothing took the user's name.
    assert not list(config.DATA_DIR.parent.rglob("*passwd*")) and not list(config.DATA_DIR.parent.rglob("*win.ini*"))
    assert sorted(p.name for p in (config.DATA_DIR / job).rglob("*") if p.is_file()) == ["merged.pdf", "result.json"]


def test_file_too_large(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_FILE_BYTES", 1000)
    r = client.post("/api/jobs", data={"tool": "merge"},
                    files=[("files", ("a.pdf", make_pdf("x") + b"\0" * 2000))] * 2)
    assert r.status_code == 413
    assert list(config.DATA_DIR.iterdir()) == [] or all(
        d.name in jobs.JOBS for d in config.DATA_DIR.iterdir())   # rejected job cleaned up


def test_too_many_files(client):
    r = client.post("/api/jobs", data={"tool": "merge"},
                    files=[("files", ("a.pdf", make_pdf("x")))] * 21)
    assert r.status_code == 400


def test_body_over_limit_is_rejected_before_parsing(client):
    r = client.post("/api/jobs", content=b"x", headers={"Content-Length": str(10**12)})
    assert r.status_code == 413


def test_unknown_tool_and_bad_options(client):
    f = [("files", ("a.pdf", make_pdf("x")))] * 2
    assert client.post("/api/jobs", data={"tool": "nope"}, files=f).status_code == 404
    assert client.post("/api/jobs", data={"tool": "merge", "options": '{"x":1}'}, files=f).status_code == 422


# --- sessions, CSRF, headers ------------------------------------------------

def test_other_session_cannot_see_or_download(client):
    from fastapi.testclient import TestClient
    from app.main import app
    job = run_job(client, "merge", [("a.pdf", make_pdf("A")), ("b.pdf", make_pdf("B"))])
    other = TestClient(app, headers=ORIGIN)  # no `with`: don't rerun startup, which wipes jobs
    assert other.get(f"/api/jobs/{job}").status_code == 404
    assert other.get(f"/api/jobs/{job}/download").status_code == 404
    assert other.delete(f"/api/jobs/{job}").status_code == 404
    assert client.get(f"/api/jobs/{job}/download").status_code == 200


def test_session_cookie_flags(client):
    r = client.get("/api/tools")
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


@pytest.mark.parametrize("origin", [None, "https://evil.example"])
def test_csrf_origin_required(client, origin):
    headers = {"Origin": origin} if origin else {}
    c = client.__class__(client.app)  # no default Origin header
    with c:
        r = c.post("/api/jobs", data={"tool": "merge"}, headers=headers,
                   files=[("files", ("a.pdf", make_pdf("x")))])
    assert r.status_code == 403


def test_security_headers(client):
    h = client.get("/api/tools").headers
    assert "default-src 'self'" in h["content-security-policy"]
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "no-referrer"


def test_download_headers_and_delete_after(client):
    job = run_job(client, "merge", [("a.pdf", make_pdf("A")), ("b.pdf", make_pdf("B"))])
    r = client.get(f"/api/jobs/{job}/download?delete=true")
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("attachment;")
    assert "sandbox" in r.headers["content-security-policy"]
    assert not (config.DATA_DIR / job).exists()
    assert client.get(f"/api/jobs/{job}").status_code == 404


def test_errors_are_generic(client):
    r = client.get("/api/jobs/" + "x" * 32)
    assert r.json() == {"detail": "Not found"}


def test_expired_jobs_are_deleted(client):
    job = run_job(client, "merge", [("a.pdf", make_pdf("A")), ("b.pdf", make_pdf("B"))])
    jobs.sweep(now=time.monotonic() + config.JOB_TTL_SECONDS + 1)
    assert job not in jobs.JOBS and not (config.DATA_DIR / job).exists()


def test_startup_wipe_only_touches_job_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    (tmp_path / ("a" * 32)).mkdir()
    (tmp_path / "keep-me").mkdir()
    jobs.wipe_data_dir()
    assert [p.name for p in tmp_path.iterdir()] == ["keep-me"]


# --- sandbox ---------------------------------------------------------------

def _in_sandbox(tmp_path, code, timeout=None):
    return asyncio.run(sandbox.run(tmp_path, [sandbox.WORKER[0], "-c", code], timeout))


def test_sandbox_has_no_network(tmp_path):
    code = ("import socket,pathlib\n"
            "for host in ('169.254.169.254', '1.1.1.1', '127.0.0.1'):\n"
            "  try: socket.create_connection((host, 80), 1); pathlib.Path('/job/leak').touch()\n"
            "  except OSError: pass")
    assert _in_sandbox(tmp_path, code) == 0
    assert not (tmp_path / "leak").exists()


def test_sandbox_cannot_see_other_jobs_or_home(tmp_path):
    other = config.DATA_DIR / ("o" * 32)
    other.mkdir(exist_ok=True)
    (other / "secret").write_text("other user's file")
    code = ("import os,json\n"
            f"paths = [{str(other)!r}, {str(config.DATA_DIR)!r}, os.path.expanduser('~ntran/.ssh'),"
            f" {str(config.BACKEND / 'tests')!r}]\n"
            "json.dump([os.path.exists(p) for p in paths], open('/job/r.json','w'))")
    assert _in_sandbox(tmp_path, code) == 0
    assert json.loads((tmp_path / "r.json").read_text()) == [False, False, False, False]


def test_sandbox_timeout_kills(tmp_path):
    t = time.monotonic()
    assert _in_sandbox(tmp_path, "while True: pass", timeout=1) is None
    assert time.monotonic() - t < 5


def test_sandbox_memory_limit(tmp_path):
    assert _in_sandbox(tmp_path, f"b = bytearray({config.JOB_MEMORY_BYTES * 2})") != 0


def test_symlinked_output_is_not_served(tmp_path):
    job = jobs.Job(owner="x", dir=tmp_path, stem="f", tool="merge")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "x.pdf").symlink_to("/etc/passwd")
    (tmp_path / "result.json").write_text('{"output": "x.pdf"}')
    assert jobs._result(job) == (None, None)
    (tmp_path / "result.json").write_text('{"output": "../../../etc/passwd"}')
    assert jobs._result(job) == (None, None)


# --- hostile files ----------------------------------------------------------

def _zip(entries: dict[str, bytes], tmp_path, symlink: str | None = None) -> Path:
    p = tmp_path / "f.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
    return p


def test_zip_bomb(tmp_path):
    with pytest.raises(UserError, match="compressed"):
        safety.check_zip(_zip({"word/document.xml": b"\0" * 50_000_000}, tmp_path))


def test_zip_slip(tmp_path):
    with pytest.raises(UserError, match="unsafe paths"):
        safety.check_zip(_zip({"../../evil.sh": b"x"}, tmp_path))
    with pytest.raises(UserError, match="unsafe paths"):
        safety.extract_zip(_zip({"/abs/evil": b"x"}, tmp_path), tmp_path / "x")


def test_zip_symlink(tmp_path):
    with pytest.raises(UserError, match="links"):
        safety.check_zip(_zip({"index.html": b"x"}, tmp_path, symlink="img.png"))


def test_zip_too_many_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MAX_ZIP_ENTRIES", 5)
    with pytest.raises(UserError, match="too many"):
        safety.check_zip(_zip({f"{i}.txt": b"x" for i in range(6)}, tmp_path))


def test_xxe_in_docx(tmp_path):
    xxe = (b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
           b'<w:document xmlns:w="w">&x;</w:document>')
    docx = _zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": xxe}, tmp_path)
    with pytest.raises(UserError, match="unsafe XML"):
        safety.check_zip(docx)


def test_billion_laughs(tmp_path):
    bomb = b'<!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><r>&b;</r>'
    with pytest.raises(UserError, match="unsafe XML"):
        safety.check_zip(_zip({"content.xml": bomb}, tmp_path))


def test_10000_page_pdf(client):
    import pymupdf
    doc = pymupdf.open()
    for _ in range(10_000):
        doc.new_page(width=10, height=10)
    job = run_job(client, "merge", [("a.pdf", doc.tobytes()), ("b.pdf", make_pdf("B"))], expect="failed")
    assert "more than 2000 pages" in client.get(f"/api/jobs/{job}").json()["error"]


def test_oversized_image(tmp_path):
    safety.harden()
    p = tmp_path / "big.png"
    Image.new("1", (12_000, 12_000)).save(p)  # 144 MP, tiny file
    with pytest.raises((Image.DecompressionBombError, Image.DecompressionBombWarning)):
        Image.open(p)


def _js_pdf() -> bytes:
    pdf = pikepdf.new()
    pdf.add_blank_page()
    js = pikepdf.Dictionary(S=pikepdf.Name.JavaScript, JS=pikepdf.String("app.alert(1)"))
    pdf.Root.OpenAction = pdf.make_indirect(js)
    pdf.Root.Names = pikepdf.Dictionary(JavaScript=pikepdf.Dictionary(
        Names=pikepdf.Array([pikepdf.String("x"), pdf.make_indirect(js)])))
    page = pdf.pages[0]
    page.AA = pikepdf.Dictionary(O=js)
    launch = pikepdf.Dictionary(S=pikepdf.Name.Launch, F=pikepdf.String("calc.exe"))
    page.Annots = pikepdf.Array([pdf.make_indirect(pikepdf.Dictionary(
        Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link, Rect=[0, 0, 10, 10], A=launch))])
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def test_javascript_is_stripped(client):
    job = run_job(client, "merge", [("a.pdf", _js_pdf()), ("b.pdf", _js_pdf())])
    out = client.get(f"/api/jobs/{job}/download").content
    assert b"app.alert" not in out and b"calc.exe" not in out
    with pikepdf.open(io.BytesIO(out)) as pdf:
        assert "/OpenAction" not in pdf.Root
        for obj in pdf.objects:
            if isinstance(obj, pikepdf.Dictionary):
                assert obj.get("/S") not in (pikepdf.Name.JavaScript, pikepdf.Name.Launch)
                assert "/JS" not in obj and "/AA" not in obj


def test_sanitize_strips_raw_pdf(tmp_path):
    p = tmp_path / "js.pdf"
    p.write_bytes(_js_pdf())
    safety.sanitize_pdf(p)
    data = p.read_bytes()
    with pikepdf.open(p) as pdf:
        assert "/OpenAction" not in pdf.Root and "/JavaScript" not in pdf.Root.Names
        assert "/AA" not in pdf.pages[0]
        assert pdf.pages[0].Annots[0].A.S == pikepdf.Name.Named


@pytest.mark.parametrize("name,expected", [
    ("Quarterly report", "Quarterly report.pdf"),
    ("../../etc/passwd", "passwd.pdf"),
    ('a"\r\nSet-Cookie: x=1', "a_Set-Cookie_ x_1.pdf"),
    ("report.exe", "report.exe.pdf"),
    ("", "a-merge.pdf"),
])
def test_custom_download_name_is_sanitized(client, name, expected):
    job = run_job(client, "merge", [("a.pdf", make_pdf("A")), ("b.pdf", make_pdf("B"))])
    assert client.get(f"/api/jobs/{job}").json() == {"status": "done", "error": None, "name": "a-merge", "ext": ".pdf"}
    r = client.get(f"/api/jobs/{job}/download", params={"name": name})
    assert _download_name(r.headers["content-disposition"]) == expected
    assert "x=1" not in r.headers.get("set-cookie", "")


def _download_name(cd: str) -> str:
    """Filename from Content-Disposition, in either the plain or the RFC 5987 (filename*=) form."""
    from urllib.parse import unquote
    assert cd.startswith("attachment; ") and "\r" not in cd and "\n" not in cd
    if "filename*=utf-8''" in cd:
        return unquote(cd.split("filename*=utf-8''", 1)[1])
    return cd.split('filename="', 1)[1].rstrip('"')
