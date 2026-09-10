# backend/app/pipeline/ingest.py
from typing import Literal, NamedTuple, Optional

import fitz
import pytesseract
from PIL import Image
from pytesseract import Output

from app.config import MIN_PDF_TEXT_LENGTH


class IngestResult(NamedTuple):
    text: str
    extraction_method: Optional[Literal["pdf_text", "ocr"]]
    ocr_confidence: Optional[float]
    readable: bool


def extract_pdf_text(doc: "fitz.Document") -> str:
    return "\n".join(page.get_text() for page in doc)


def _image_to_text_and_confidence(image: Image.Image) -> tuple[str, float]:
    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    words = [w for w in data["text"] if w.strip()]
    confidences = [int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) >= 0]
    text = " ".join(words)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return text, avg_confidence


def rasterize_and_ocr_pdf(doc: "fitz.Document") -> tuple[str, float]:
    texts = []
    confidences = []
    for page in doc:
        pixmap = page.get_pixmap()
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        text, confidence = _image_to_text_and_confidence(image)
        texts.append(text)
        confidences.append(confidence)
    combined_text = "\n".join(texts)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return combined_text, avg_confidence


def ocr_image(image_bytes: bytes) -> tuple[str, float]:
    import io

    image = Image.open(io.BytesIO(image_bytes))
    return _image_to_text_and_confidence(image)


def ingest_document(file_bytes: bytes, filename: str) -> IngestResult:
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception:
            return IngestResult(text="", extraction_method=None, ocr_confidence=None, readable=False)

        text = extract_pdf_text(doc)
        alnum_count = sum(1 for ch in text if ch.isalnum())
        if alnum_count >= MIN_PDF_TEXT_LENGTH:
            doc.close()
            return IngestResult(text=text, extraction_method="pdf_text", ocr_confidence=None, readable=True)

        ocr_text, confidence = rasterize_and_ocr_pdf(doc)
        doc.close()
        readable = bool(ocr_text.strip())
        return IngestResult(text=ocr_text, extraction_method="ocr", ocr_confidence=confidence, readable=readable)

    if lower_name.endswith((".png", ".jpg", ".jpeg")):
        try:
            text, confidence = ocr_image(file_bytes)
        except Exception:
            return IngestResult(text="", extraction_method=None, ocr_confidence=None, readable=False)
        readable = bool(text.strip())
        return IngestResult(text=text, extraction_method="ocr", ocr_confidence=confidence, readable=readable)

    return IngestResult(text="", extraction_method=None, ocr_confidence=None, readable=False)
