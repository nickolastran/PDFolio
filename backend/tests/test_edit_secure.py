import io
import json

import pikepdf
import pymupdf
import pytest
from PIL import Image

from app import config
from conftest import make_pdf, run_job
from test_security import _js_pdf


def dl(client, job) -> bytes:
    return client.get(f"/api/jobs/{job}/download").content


def opened(data: bytes) -> pymupdf.Document:
    return pymupdf.open(stream=data, filetype="pdf")


def _png(size=(200, 100), color=(0, 0, 0, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def _rotated_pdf() -> bytes:
    doc = pymupdf.open(stream=make_pdf("Rotated"), filetype="pdf")
    doc[0].set_rotation(90)
    return doc.tobytes()


# --- edit -----------------------------------------------------------------

def test_page_numbers(client):
    opts = {"format": "page_n_of_total", "start": 3, "position": "bottom-right"}
    doc = opened(dl(client, run_job(client, "page-numbers", [("a.pdf", make_pdf("A", "B"))], json.dumps(opts))))
    assert "Page 3 of 4" in doc[0].get_text() and "Page 4 of 4" in doc[1].get_text()
    (x0, y0, x1, y1, *_), = [b for b in doc[0].get_text("blocks") if "Page 3" in b[4]]
    assert y0 > doc[0].rect.height * 0.8 and x1 > doc[0].rect.width * 0.8


def test_page_numbers_on_rotated_page_sit_at_visual_bottom(client):
    doc = opened(dl(client, run_job(client, "page-numbers", [("a.pdf", _rotated_pdf())])))
    page = doc[0]
    block = [b for b in page.get_text("blocks") if b[4].strip() == "1"][0]
    visual = pymupdf.Rect(block[:4]) * page.rotation_matrix
    assert visual.y0 > page.rect.height * 0.8


def test_text_watermark(client):
    doc = opened(dl(client, run_job(client, "watermark", [("a.pdf", make_pdf("Body"))], '{"text": "DRAFT", "opacity": 20}')))
    assert "DRAFT" in doc[0].get_text()
    with pikepdf.open(io.BytesIO(doc.tobytes())) as pdf:
        states = pdf.pages[0].Resources.ExtGState
        assert any(float(gs.get("/ca", 1)) == 0.2 for gs in states.values())


def test_image_watermark(client):
    job = run_job(client, "watermark", [("a.pdf", make_pdf("Body")), ("logo.png", _png())], '{"mode": "image"}')
    assert opened(dl(client, job))[0].get_images()


def test_image_watermark_needs_image(client):
    job = run_job(client, "watermark", [("a.pdf", make_pdf("Body"))], '{"mode": "image"}', expect="failed")
    assert client.get(f"/api/jobs/{job}").json()["error"] == "Add an image to use as the watermark"


@pytest.mark.parametrize("pdf", [make_pdf("x"), _rotated_pdf()], ids=["upright", "rotated"])
def test_crop(client, pdf):
    before = opened(pdf)[0].rect
    after = opened(dl(client, run_job(client, "crop", [("a.pdf", pdf)], '{"top": 20, "right": 0, "bottom": 0, "left": 10}')))[0].rect
    mm = 72 / 25.4
    assert after.height == pytest.approx(before.height - 20 * mm, abs=0.5)
    assert after.width == pytest.approx(before.width - 10 * mm, abs=0.5)


def test_crop_too_much(client):
    job = run_job(client, "crop", [("a.pdf", make_pdf("x"))], '{"top": 400, "bottom": 400}', expect="failed")
    assert client.get(f"/api/jobs/{job}").json()["error"] == "Margins are larger than the page"


def test_annotate(client):
    notes = [{"page": 1, "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.1, "text": "Check this"}]
    doc = opened(dl(client, run_job(client, "annotate", [("a.pdf", make_pdf("1", "2"))], json.dumps({"notes": notes}))))
    (annot,) = list(doc[1].annots())
    assert annot.info["content"] == "Check this"
    assert not list(doc[0].annots())


def _form_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    for name, kind, y in (("name", pymupdf.PDF_WIDGET_TYPE_TEXT, 72), ("agree", pymupdf.PDF_WIDGET_TYPE_CHECKBOX, 120)):
        w = pymupdf.Widget()
        w.field_name, w.field_type, w.rect = name, kind, pymupdf.Rect(72, y, 272, y + 24)
        page.add_widget(w)
    return doc.tobytes()


def test_fill_form(client):
    job = run_job(client, "fill-form", [("f.pdf", _form_pdf())], '{"values": {"name": "Ada", "agree": true}}')
    values = {w.field_name: w.field_value for w in opened(dl(client, job))[0].widgets()}
    assert values["name"] == "Ada" and values["agree"] not in ("Off", False, "")


def test_fill_form_without_fields(client):
    job = run_job(client, "fill-form", [("a.pdf", make_pdf("x"))], '{"values": {}}', expect="failed")
    assert client.get(f"/api/jobs/{job}").json()["error"] == "This PDF has no form fields"


# --- protect / unlock --------------------------------------------------------

def test_protect_aes256_and_sanitized(client):
    data = dl(client, run_job(client, "protect", [("a.pdf", _js_pdf())], '{"password": "correct horse"}'))
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(io.BytesIO(data))
    with pikepdf.open(io.BytesIO(data), password="correct horse") as pdf:
        assert pdf.encryption.R == 6 and pdf.encryption.bits == 256
        assert pdf.encryption.stream_method.name == "aesv3"   # AES-256
        assert "/OpenAction" not in pdf.Root


def test_protect_password_too_short(client):
    r = client.post("/api/jobs", data={"tool": "protect", "options": '{"password": "abc"}'},
                    files=[("files", ("a.pdf", make_pdf("x")))])
    assert r.status_code == 422


def _locked(pw="s3cret!") -> bytes:
    buf = io.BytesIO()
    with pikepdf.open(io.BytesIO(make_pdf("Locked text"))) as pdf:
        pdf.save(buf, encryption=pikepdf.Encryption(user=pw, owner=pw, R=6))
    return buf.getvalue()


def test_unlock_with_correct_password(client):
    data = dl(client, run_job(client, "unlock", [("a.pdf", _locked())], '{"password": "s3cret!"}'))
    assert not opened(data).needs_pass and "Locked text" in opened(data)[0].get_text()


def test_unlock_wrong_password(client):
    job = run_job(client, "unlock", [("a.pdf", _locked())], '{"password": "guess"}', expect="failed")
    assert client.get(f"/api/jobs/{job}").json()["error"] == "Wrong password"


def test_other_tools_refuse_locked_pdfs(client):
    job = run_job(client, "page-numbers", [("a.pdf", _locked())], expect="failed")
    assert "Unlock it first" in client.get(f"/api/jobs/{job}").json()["error"]


def test_password_does_not_stay_on_disk(client):
    job = run_job(client, "unlock", [("a.pdf", _locked())], '{"password": "s3cret!"}')
    files = [p for p in (config.DATA_DIR / job).rglob("*") if p.is_file()]
    assert sorted(p.name for p in files) == ["result.json", "unlocked.pdf"]
    assert all(b"s3cret!" not in p.read_bytes() for p in files)


# --- sign -------------------------------------------------------------------

def test_sign_places_image(client):
    places = [{"page": 1, "x": 0.6, "y": 0.8, "w": 0.3, "h": 0.1}]
    job = run_job(client, "sign", [("a.pdf", make_pdf("1", "2")), ("sig.png", _png())], json.dumps({"places": places}))
    doc = opened(dl(client, job))
    assert not doc[0].get_images()
    (img,) = doc[1].get_image_info()
    r = doc[1].rect
    assert img["bbox"][0] >= r.width * 0.6 - 1 and img["bbox"][1] >= r.height * 0.8 - 1


def test_sign_needs_pdf_and_image(client):
    job = run_job(client, "sign", [("a.pdf", make_pdf("1")), ("b.pdf", make_pdf("2"))],
                  '{"places": [{"page": 0, "x": 0, "y": 0, "w": 0.1, "h": 0.1}]}', expect="failed")
    assert client.get(f"/api/jobs/{job}").json()["error"] == "Add one PDF and one signature image"


# --- redact -----------------------------------------------------------------

def _secret_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Account SECRET-4242 belongs to Ada")
    page.insert_text((72, 300), "Area text to hide")
    page.insert_text((72, 500), "Public paragraph")
    doc.set_metadata({"title": "SECRET-4242 report", "author": "Ada"})
    page.add_text_annot((300, 300), "SECRET-4242 in a note")
    return doc.tobytes()


def _all_bytes(data: bytes) -> bytes:
    """Every object and decompressed stream: what someone digging through the file would see."""
    out = []
    with pikepdf.open(io.BytesIO(data)) as pdf:
        for obj in pdf.objects:
            out.append(repr(obj).encode())
            if isinstance(obj, pikepdf.Stream):
                try:
                    out.append(obj.read_bytes())
                except pikepdf.PdfError:
                    out.append(obj.read_raw_bytes())
        out.append(repr(pdf.trailer).encode())
    return b"".join(out)


def test_redaction_is_unrecoverable(client):
    page = pymupdf.open(stream=_secret_pdf(), filetype="pdf")[0]
    area = page.search_for("Area text to hide")[0]
    box = {"page": 0, "x": area.x0 / page.rect.width, "y": area.y0 / page.rect.height,
           "w": area.width / page.rect.width, "h": area.height / page.rect.height}
    job = run_job(client, "redact", [("a.pdf", _secret_pdf())], json.dumps({"terms": ["secret-4242"], "areas": [box]}))
    data = dl(client, job)
    doc = opened(data)
    text = doc[0].get_text()
    assert "SECRET-4242" not in text and "Area text" not in text
    assert "Public paragraph" in text and "belongs to Ada" in text
    raw = _all_bytes(data)
    assert b"SECRET-4242" not in raw and b"Area text" not in raw   # not in streams, metadata or notes
    assert doc.metadata.get("title", "") == ""


def test_redaction_needs_something(client):
    job = run_job(client, "redact", [("a.pdf", make_pdf("x"))], '{"terms": ["nothing here"]}')
    assert "x" in opened(dl(client, job))[0].get_text()


# --- compare ----------------------------------------------------------------

def test_compare_report(client):
    a = make_pdf("Same page", "Old wording")
    b = make_pdf("Same page", "New wording")
    doc = opened(dl(client, run_job(client, "compare", [("a.pdf", a), ("b.pdf", b)])))
    text = "\n".join(p.get_text() for p in doc)
    assert "1 page looks different" in doc[0].get_text()
    assert "-Old wording" in text and "+New wording" in text
    assert doc.page_count == 1 + 2 + 1   # summary, two side-by-side pages, one text-diff page
