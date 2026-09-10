# backend/tests/test_integration.py
import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _upload(filename: str, content_type: str):
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "rb") as f:
        response = client.post("/extract", files={"file": (filename, f, content_type)})
    return response


def test_clean_pdf_returns_ok_status():
    response = _upload("synthetic_clean.pdf", "application/pdf")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["tipo_comprobante"] == "A"
    assert body["data"]["total"] == 12100.0


def test_mismatch_pdf_returns_partial_with_total_mismatch_warning():
    response = _upload("synthetic_mismatch.pdf", "application/pdf")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    codes = [w["code"] for w in body["warnings"]]
    assert "TOTAL_MISMATCH" in codes


def test_unreadable_image_returns_failed():
    response = _upload("synthetic_unreadable.png", "image/png")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["errors"][0]["code"] == "UNREADABLE_DOCUMENT"


def test_missing_file_returns_400():
    response = client.post("/extract", files={})
    assert response.status_code in (400, 422)


def test_response_always_has_data_key_even_when_failed():
    response = _upload("synthetic_unreadable.png", "image/png")
    body = response.json()
    assert "data" in body
    assert body["data"]["moneda"] == "ARS"
