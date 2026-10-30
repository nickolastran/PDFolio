import io
import json
import zipfile

import pymupdf
import pytest
from PIL import Image

from app.ops.organize import parse_ranges
from app.tools import UserError
from conftest import make_pdf, pdf_texts, run_job


def download(client, job):
    return client.get(f"/api/jobs/{job}/download").content


def plan(client, tool, files, pages, **extra):
    job = run_job(client, tool, files, json.dumps({"pages": pages, **extra}))
    return pymupdf.open(stream=download(client, job), filetype="pdf")


def test_merge_keeps_upload_order(client):
    files = [("b.pdf", make_pdf("B1", "B2")), ("a.pdf", make_pdf("A1")), ("c.pdf", make_pdf("C1"))]
    job = run_job(client, "merge", files)
    assert pdf_texts(download(client, job)) == ["B1", "B2", "A1", "C1"]


@pytest.mark.parametrize("text,expected", [
    ("1-3, 4-7, 8-end", [(0, 2), (3, 6), (7, 9)]),
    ("2", [(1, 1)]),
    (" 5 - END ,", [(4, 9)]),
    ("end", [(9, 9)]),
])
def test_parse_ranges(text, expected):
    assert parse_ranges(text, 10) == expected


@pytest.mark.parametrize("text", ["0-2", "3-1", "1-11", "abc", "1-2-3", "", " , "])
def test_parse_ranges_rejects(text):
    with pytest.raises(UserError):
        parse_ranges(text, 10)


def _zip_texts(data: bytes) -> dict[str, list[str]]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {n: pdf_texts(zf.read(n)) for n in zf.namelist()}


@pytest.mark.parametrize("opts,expected", [
    ({"mode": "ranges", "ranges": "1-2, 3-end"},
     {"001-pages-1-2.pdf": ["P1", "P2"], "002-pages-3-5.pdf": ["P3", "P4", "P5"]}),
    ({"mode": "every", "every": 2},
     {"001-pages-1-2.pdf": ["P1", "P2"], "002-pages-3-4.pdf": ["P3", "P4"], "003-page-5.pdf": ["P5"]}),
    ({"mode": "each"}, {f"00{i}-page-{i}.pdf": [f"P{i}"] for i in range(1, 6)}),
])
def test_split(client, opts, expected):
    job = run_job(client, "split", [("a.pdf", make_pdf(*[f"P{i}" for i in range(1, 6)]))], json.dumps(opts))
    r = client.get(f"/api/jobs/{job}/download")
    assert r.headers["content-type"] == "application/zip"
    assert _zip_texts(r.content) == expected


def test_split_bad_range_is_user_error(client):
    job = run_job(client, "split", [("a.pdf", make_pdf("1"))], '{"ranges": "2-3"}', expect="failed")
    assert "outside pages 1–1" in client.get(f"/api/jobs/{job}").json()["error"]


def test_organize_reorder_rotate_duplicate_blank_across_files(client):
    files = [("a.pdf", make_pdf("A1", "A2")), ("b.pdf", make_pdf("B1"))]
    doc = plan(client, "organize", files, [
        {"file": 1, "page": 0},
        {"file": 0, "page": 1, "rotate": 90},
        {"blank": True},
        {"file": 0, "page": 1},
    ])
    assert [p.get_text().strip() for p in doc] == ["B1", "A2", "", "A2"]
    assert [p.rotation for p in doc] == [0, 90, 0, 0]


def test_remove_and_extract(client):
    f = [("a.pdf", make_pdf("1", "2", "3", "4"))]
    # The page grid sends the pages to keep; remove and extract differ only in the UI.
    assert [p.get_text().strip() for p in plan(client, "remove", f, [{"page": 0}, {"page": 3}])] == ["1", "4"]
    assert [p.get_text().strip() for p in plan(client, "extract", f, [{"page": 2}])] == ["3"]


def test_rotate_adds_to_existing_rotation(client):
    src = pymupdf.open(stream=make_pdf("x"), filetype="pdf")
    src[0].set_rotation(90)
    doc = plan(client, "rotate", [("a.pdf", src.tobytes())], [{"page": 0, "rotate": 270}])
    assert doc[0].rotation == 0


def test_orientation_landscape(client):
    doc = plan(client, "rotate", [("a.pdf", make_pdf("portrait"))], [{"page": 0}], orientation="landscape")
    assert doc[0].rect.width > doc[0].rect.height
    assert "portrait" in doc[0].get_text()


def test_plan_page_out_of_range(client):
    job = run_job(client, "organize", [("a.pdf", make_pdf("1"))], '{"pages": [{"page": 5}]}', expect="failed")
    assert client.get(f"/api/jobs/{job}").json()["error"] == "Page selection doesn't match the file"


def _jpeg_with_exif(size, orientation) -> bytes:
    im = Image.new("RGB", size, "white")
    exif = Image.Exif()
    exif[0x0112] = orientation                 # Orientation
    exif[0x010F] = "SecretCam"                 # Make, stands in for GPS/location data
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_images_to_pdf_respects_exif_rotation_and_strips_metadata(client):
    sideways = _jpeg_with_exif((400, 200), 6)  # stored landscape, displayed portrait
    png = io.BytesIO()
    Image.new("RGBA", (300, 300)).save(png, "PNG")
    job = run_job(client, "scan", [("photo.jpg", sideways), ("b.png", png.getvalue())], '{"page_size": "a4"}')
    data = download(client, job)
    doc = pymupdf.open(stream=data, filetype="pdf")
    assert doc.page_count == 2
    assert doc[0].rect.height > doc[0].rect.width
    assert b"SecretCam" not in data


def test_images_fit_page_matches_aspect(client):
    job = run_job(client, "jpg-to-pdf", [("a.jpg", _jpeg_with_exif((800, 400), 1))])
    r = pymupdf.open(stream=download(client, job), filetype="pdf")[0].rect
    assert round(r.width / r.height, 2) == 2.0


def test_oversized_image_via_api(client):
    buf = io.BytesIO()
    Image.new("1", (12_000, 12_000)).save(buf, "PNG")
    job = run_job(client, "scan", [("big.png", buf.getvalue())], expect="failed")
    assert client.get(f"/api/jobs/{job}").json()["error"] == "Image is too large"
