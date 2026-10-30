import os
import tempfile
import time

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="pdfjobs-")
os.environ["COOKIE_SECURE"] = "false"   # TestClient talks plain http
os.environ["RATE_LIMIT"] = "1000/minute"

import pymupdf  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ORIGIN = {"Origin": "http://localhost:8000"}


def make_pdf(*texts: str) -> bytes:
    """One page per text, so tests can check page order by extracting text."""
    doc = pymupdf.open()
    for t in texts:
        doc.new_page().insert_text((72, 72), t)
    return doc.tobytes()


def pdf_texts(data: bytes) -> list[str]:
    return [p.get_text().strip() for p in pymupdf.open(stream=data, filetype="pdf")]


@pytest.fixture
def client():
    with TestClient(app, headers=ORIGIN) as c:
        yield c


def run_job(client, tool, files, options="{}", expect="done"):
    """files: list of (name, bytes). Returns the job id once it finishes."""
    r = client.post("/api/jobs", data={"tool": tool, "options": options},
                    files=[("files", (n, b)) for n, b in files])
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    for _ in range(600):
        s = client.get(f"/api/jobs/{job_id}").json()
        if s["status"] in ("done", "failed"):
            assert s["status"] == expect, s
            return job_id
        time.sleep(0.1)
    raise AssertionError("job did not finish")
