# backend/tests/test_ingest.py
import io

import pymupdf as fitz
from PIL import Image, ImageDraw

from app.pipeline.ingest import ingest_document


def _make_text_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _make_blank_pdf_bytes() -> bytes:
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def _make_out_of_order_text_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 144), "Importe Total: $ 12100,00")
    page.insert_text((72, 72), "FACTURA A")
    data = doc.tobytes()
    doc.close()
    return data


def _make_text_image_bytes(text: str) -> bytes:
    img = Image.new("RGB", (400, 100), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 40), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_blank_image_bytes() -> bytes:
    img = Image.new("RGB", (100, 100), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_pdf_with_embedded_text_uses_pdf_text_method():
    pdf_bytes = _make_text_pdf_bytes("FACTURA A Total: $12100.00 CUIT 20-12345678-9")
    result = ingest_document(pdf_bytes, "invoice.pdf")
    assert result.extraction_method == "pdf_text"
    assert result.readable is True
    assert "FACTURA" in result.text
    assert result.ocr_confidence is None


def test_pdf_embedded_text_is_returned_in_visual_reading_order():
    result = ingest_document(_make_out_of_order_text_pdf_bytes(), "invoice.pdf")

    assert result.text.index("FACTURA A") < result.text.index("Importe Total")


def test_scanned_pdf_falls_back_to_ocr():
    pdf_bytes = _make_blank_pdf_bytes()
    result = ingest_document(pdf_bytes, "scanned.pdf")
    assert result.extraction_method == "ocr"


def test_image_runs_ocr():
    img_bytes = _make_text_image_bytes("TOTAL 100")
    result = ingest_document(img_bytes, "invoice.png")
    assert result.extraction_method == "ocr"
    assert result.ocr_confidence is not None


def test_blank_image_is_unreadable():
    img_bytes = _make_blank_image_bytes()
    result = ingest_document(img_bytes, "blank.png")
    # Assert extraction_method == "ocr" (not just readable is False) so this
    # test can only pass if OCR genuinely ran and found no usable text --
    # not if Tesseract was simply unavailable (which would silently swallow
    # TesseractNotFoundError and leave extraction_method as None).
    assert result.extraction_method == "ocr"
    assert result.readable is False


def test_unsupported_extension_returns_unreadable():
    result = ingest_document(b"not a real file", "invoice.txt")
    assert result.readable is False
    assert result.extraction_method is None


def test_corrupt_pdf_bytes_returns_unreadable():
    result = ingest_document(b"this is not a pdf", "broken.pdf")
    assert result.readable is False
    assert result.extraction_method is None
