# Extractor de Facturas ARCA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an end-to-end pipeline that extracts structured JSON data from
Argentine ARCA/AFIP invoices (PDF or image), with explicit validation and
explicit handling of failed/ambiguous extraction, exposed via a FastAPI
backend and a minimal Next.js frontend.

**Architecture:** A synchronous FastAPI backend runs a 3-stage pipeline
(ingest → extract_fields → validate) per uploaded file and returns a single
JSON response. Field extraction is rule-based (regex/heuristics), not
LLM-based. A minimal Next.js single-page frontend uploads a file, renders the
JSON result, and keeps an in-memory (non-persisted) history for the session.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, PyMuPDF (`pymupdf`/`fitz`),
pytesseract (+ system Tesseract binary), Pydantic v2, pytest. Next.js (App
Router, TypeScript), no UI framework required (Tailwind optional).

**Spec:** `docs/superpowers/specs/2026-09-09-invoice-extractor-design.md`

## Global Constraints

- Python 3.11+ for the backend; Next.js App Router (TypeScript) for the frontend.
- Only dependency for PDF handling is PyMuPDF (`pymupdf`) — do not add `pdf2image`, `PyPDF2`, or `pypdf`.
- OCR is Tesseract via `pytesseract` only — no cloud OCR APIs, no GLM-OCR, no LLM calls anywhere in the pipeline.
- Field structuring is regex/heuristics only — never inject an LLM call into `extract_fields.py`.
- `POST /extract` always returns HTTP 200 when the pipeline ran; business failure is communicated via `status: "failed"` in the JSON body, never via HTTP error codes. HTTP 4xx is reserved for malformed requests (missing file, bad content type, oversized file).
- Never fabricate a field value — a field that can't be confidently extracted must be `null`, with a corresponding warning/error entry, never a guessed value.
- CORS must allow `http://localhost:3000` in development.
- Frontend has no server-side persistence and no database; history lives only in React state for the session.
- All monetary tolerance comparisons use ±1% relative tolerance (for rounding).
- Numbered field/warning/error codes and the JSON response shape (Section 5 of the spec) are exact contracts — every task producing or consuming this JSON must match those field names precisely.

---

## File Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app + POST /extract endpoint
│   ├── config.py                # thresholds, tolerances, regex constants
│   ├── models/
│   │   ├── __init__.py
│   │   └── invoice.py           # Pydantic schemas: LineItem, InvoiceData, Warning, ErrorDetail, ExtractionResult
│   └── pipeline/
│       ├── __init__.py
│       ├── ingest.py            # file type detection, PyMuPDF text/rasterize, Tesseract OCR
│       ├── extract_fields.py    # regex/heuristics: header fields + items from plain text
│       └── validate.py          # Pydantic validation + numeric consistency + status determination
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   ├── README.md            # instructions for adding real anonymized invoices later
│   │   ├── synthetic_clean.pdf          # generated in Task 6
│   │   ├── synthetic_low_confidence.png # generated in Task 6
│   │   ├── synthetic_mismatch.pdf       # generated in Task 6
│   │   └── synthetic_unreadable.png     # generated in Task 6
│   ├── test_ingest.py
│   ├── test_extract_fields.py
│   ├── test_validate.py
│   └── test_integration.py
├── requirements.txt
└── README.md

frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                 # single page: upload + result + history
│   └── globals.css
├── components/
│   ├── UploadForm.tsx
│   ├── ResultView.tsx
│   └── HistoryList.tsx
├── lib/
│   ├── api.ts                   # fetch wrapper for POST /extract
│   └── types.ts                 # TypeScript types mirroring backend ExtractionResult
├── package.json
├── tsconfig.json
├── next.config.js
├── .env.local.example
└── README.md

README.md                        # root overview: setup, design decisions, limitations, roadmap
```

---

## Task 1: Pydantic models (`invoice.py`)

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/invoice.py`
- Test: `backend/tests/test_validate.py` (model-level tests only in this task; validation-logic tests come in Task 4)

**Interfaces:**
- Consumes: nothing (first task).
- Produces (used by all later backend tasks):
  - `LineItem(descripcion: str, cantidad: float, precio_unitario: float, subtotal_linea: float)`
  - `InvoiceData` — all fields optional (`Optional[...] = None`), matching spec Section 5 `data` object exactly:
    `tipo_comprobante: Optional[str]`, `punto_venta: Optional[str]`, `numero_comprobante: Optional[str]`,
    `fecha_emision: Optional[str]` (ISO `YYYY-MM-DD` string), `cuit_emisor: Optional[str]`,
    `razon_social_emisor: Optional[str]`, `cuit_receptor: Optional[str]`, `razon_social_receptor: Optional[str]`,
    `condicion_iva_receptor: Optional[str]`, `cae: Optional[str]`, `vencimiento_cae: Optional[str]`,
    `moneda: str = "ARS"`, `subtotal: Optional[float]`, `iva: Optional[float]`, `total: Optional[float]`,
    `items: list[LineItem] = []`
  - `Warning(code: str, field: Optional[str], message: str)`
  - `ErrorDetail(code: str, field: Optional[str], message: str)`
  - `ExtractionResult(status: Literal["ok","partial","failed"], extraction_method: Optional[Literal["pdf_text","ocr"]], ocr_confidence: Optional[float], data: InvoiceData, field_confidence: dict[str, Literal["high","medium","low"]], warnings: list[Warning], errors: list[ErrorDetail])`
  - `FieldConfidence = Literal["high", "medium", "low"]` type alias, exported for reuse.

Use Pydantic v2 (`from pydantic import BaseModel, Field`). `InvoiceData` fields are all `Optional` because the pipeline must be able to emit partial data — do not add `Field(...)` (required) markers on `InvoiceData` fields; obligatoriedad is enforced later in `validate.py`, not at the schema level.

- [ ] **Step 1: Create package init files**

Create `backend/app/models/__init__.py` (empty file) and ensure `backend/app/__init__.py` exists (empty file, create if missing).

- [ ] **Step 2: Write `invoice.py` models**

```python
# backend/app/models/invoice.py
from typing import Literal, Optional

from pydantic import BaseModel, Field

FieldConfidence = Literal["high", "medium", "low"]
ExtractionStatus = Literal["ok", "partial", "failed"]
ExtractionMethod = Literal["pdf_text", "ocr"]


class LineItem(BaseModel):
    descripcion: str
    cantidad: float
    precio_unitario: float
    subtotal_linea: float


class InvoiceData(BaseModel):
    tipo_comprobante: Optional[str] = None
    punto_venta: Optional[str] = None
    numero_comprobante: Optional[str] = None
    fecha_emision: Optional[str] = None
    cuit_emisor: Optional[str] = None
    razon_social_emisor: Optional[str] = None
    cuit_receptor: Optional[str] = None
    razon_social_receptor: Optional[str] = None
    condicion_iva_receptor: Optional[str] = None
    cae: Optional[str] = None
    vencimiento_cae: Optional[str] = None
    moneda: str = "ARS"
    subtotal: Optional[float] = None
    iva: Optional[float] = None
    total: Optional[float] = None
    items: list[LineItem] = Field(default_factory=list)


class Warning(BaseModel):
    code: str
    field: Optional[str] = None
    message: str


class ErrorDetail(BaseModel):
    code: str
    field: Optional[str] = None
    message: str


class ExtractionResult(BaseModel):
    status: ExtractionStatus
    extraction_method: Optional[ExtractionMethod] = None
    ocr_confidence: Optional[float] = None
    data: InvoiceData
    field_confidence: dict[str, FieldConfidence] = Field(default_factory=dict)
    warnings: list[Warning] = Field(default_factory=list)
    errors: list[ErrorDetail] = Field(default_factory=list)
```

- [ ] **Step 3: Write a smoke test for the models**

Create `backend/tests/__init__.py` (empty) and `backend/tests/test_validate.py` with:

```python
# backend/tests/test_validate.py
from app.models.invoice import ExtractionResult, InvoiceData, LineItem, Warning


def test_extraction_result_serializes_with_minimal_data():
    result = ExtractionResult(
        status="failed",
        extraction_method=None,
        ocr_confidence=None,
        data=InvoiceData(),
        field_confidence={},
        warnings=[],
        errors=[],
    )
    payload = result.model_dump()
    assert payload["status"] == "failed"
    assert payload["data"]["moneda"] == "ARS"
    assert payload["data"]["items"] == []


def test_extraction_result_with_full_data_and_item():
    item = LineItem(
        descripcion="Servicio de consultoría",
        cantidad=1,
        precio_unitario=10000.0,
        subtotal_linea=10000.0,
    )
    data = InvoiceData(
        tipo_comprobante="A",
        subtotal=10000.0,
        iva=2100.0,
        total=12100.0,
        items=[item],
    )
    result = ExtractionResult(
        status="ok",
        extraction_method="pdf_text",
        ocr_confidence=None,
        data=data,
        field_confidence={"tipo_comprobante": "high"},
        warnings=[Warning(code="X", field=None, message="m")],
        errors=[],
    )
    payload = result.model_dump()
    assert payload["data"]["items"][0]["descripcion"] == "Servicio de consultoría"
    assert payload["warnings"][0]["code"] == "X"
```

- [ ] **Step 4: Set up backend project scaffolding so tests can run**

Create `backend/requirements.txt`:

```
fastapi>=0.115
uvicorn[standard]>=0.30
pymupdf>=1.24
pytesseract>=0.3.13
pillow>=10.4
pydantic>=2.8
pytest>=8.3
httpx>=0.27
python-multipart>=0.0.9
```

Create `backend/pytest.ini`:

```ini
[pytest]
pythonpath = .
```

From `backend/`, run:

```bash
python -m venv .venv
```

Windows activation: `.venv\Scripts\activate` — PowerShell: `.venv\Scripts\Activate.ps1`. Then:

```bash
pip install -r requirements.txt
```

- [ ] **Step 5: Run the test to verify it passes**

Run (from `backend/`, with venv active): `pytest tests/test_validate.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/__init__.py backend/app/models/__init__.py backend/app/models/invoice.py backend/tests/__init__.py backend/tests/test_validate.py backend/requirements.txt backend/pytest.ini
git commit -m "feat(backend): add Pydantic models for extraction result"
```

Note: `.venv/` must not be committed — create `backend/.gitignore` with `.venv/`, `__pycache__/`, `*.pyc` before staging, and add it to the same commit.

---

## Task 2: Config constants (`config.py`)

**Files:**
- Create: `backend/app/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces (used by `ingest.py`, `extract_fields.py`, `validate.py`):
  - `MIN_PDF_TEXT_LENGTH: int = 20` — minimum alphanumeric character count to treat a PDF page's extracted text as usable (i.e., not a scanned PDF).
  - `LOW_OCR_CONFIDENCE_THRESHOLD: float = 40.0` — below this average OCR confidence (0-100), emit `LOW_OCR_CONFIDENCE` warning.
  - `AMOUNT_TOLERANCE_RATIO: float = 0.01` — relative tolerance for numeric consistency checks (±1%).
  - `REQUIRED_HEADER_FIELDS: list[str] = ["tipo_comprobante", "punto_venta", "numero_comprobante", "fecha_emision", "cuit_emisor", "razon_social_emisor", "subtotal", "total"]` — matches spec Section 4.2 "Obligatorio: Sí" rows exactly.
  - `CUIT_PATTERN: str = r"\d{2}-\d{8}-\d{1}"`
  - `CAE_PATTERN: str = r"\d{14}"`
  - `DATE_PATTERN: str = r"\d{2}/\d{2}/\d{4}"`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config.py
from app import config


def test_config_constants_exist_with_expected_types():
    assert isinstance(config.MIN_PDF_TEXT_LENGTH, int)
    assert isinstance(config.LOW_OCR_CONFIDENCE_THRESHOLD, float)
    assert isinstance(config.AMOUNT_TOLERANCE_RATIO, float)
    assert "total" in config.REQUIRED_HEADER_FIELDS
    assert "subtotal" in config.REQUIRED_HEADER_FIELDS
    import re
    re.compile(config.CUIT_PATTERN)
    re.compile(config.CAE_PATTERN)
    re.compile(config.DATE_PATTERN)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError` or `AttributeError` (config.py doesn't exist yet).

- [ ] **Step 3: Write `config.py`**

```python
# backend/app/config.py
MIN_PDF_TEXT_LENGTH = 20
LOW_OCR_CONFIDENCE_THRESHOLD = 40.0
AMOUNT_TOLERANCE_RATIO = 0.01

REQUIRED_HEADER_FIELDS = [
    "tipo_comprobante",
    "punto_venta",
    "numero_comprobante",
    "fecha_emision",
    "cuit_emisor",
    "razon_social_emisor",
    "subtotal",
    "total",
]

CUIT_PATTERN = r"\d{2}-\d{8}-\d{1}"
CAE_PATTERN = r"\d{14}"
DATE_PATTERN = r"\d{2}/\d{2}/\d{4}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat(backend): add pipeline config constants"
```

---

## Task 3: Ingest stage (`ingest.py`)

**Files:**
- Create: `backend/app/pipeline/__init__.py`
- Create: `backend/app/pipeline/ingest.py`
- Test: `backend/tests/test_ingest.py`

**Interfaces:**
- Consumes: `app.config.MIN_PDF_TEXT_LENGTH`.
- Produces (used by `main.py` and `extract_fields.py`/`validate.py` via the result it returns):
  - `class IngestResult(NamedTuple): text: str; extraction_method: Optional[Literal["pdf_text","ocr"]]; ocr_confidence: Optional[float]; readable: bool`
  - `def ingest_document(file_bytes: bytes, filename: str) -> IngestResult` — top-level entry point. Detects PDF vs image by filename extension (`.pdf` → PDF path; `.png`/`.jpg`/`.jpeg` → image path; anything else → `IngestResult(text="", extraction_method=None, ocr_confidence=None, readable=False)`).
  - `def extract_pdf_text(doc: "fitz.Document") -> str` — concatenates `page.get_text()` across all pages.
  - `def rasterize_and_ocr_pdf(doc: "fitz.Document") -> tuple[str, float]` — renders each page via `page.get_pixmap()`, converts to a `PIL.Image`, runs Tesseract, returns concatenated text and the average confidence across all pages/words.
  - `def ocr_image(image_bytes: bytes) -> tuple[str, float]` — opens bytes with `PIL.Image.open`, runs Tesseract via `pytesseract.image_to_data(image, output_type=Output.DICT)`, returns text (joined non-empty `text` entries) and average confidence (mean of `conf` values that are `>= 0`, since Tesseract reports `-1` for non-text regions; if no valid confidence values exist, return `0.0`).

`ingest_document` behavior:
1. `.pdf` → open with `fitz.open(stream=file_bytes, filetype="pdf")` in a `try/except`; on any exception, return `IngestResult(text="", extraction_method=None, ocr_confidence=None, readable=False)`.
2. Call `extract_pdf_text(doc)`. Strip whitespace and count alphanumeric characters; if count `>= MIN_PDF_TEXT_LENGTH`, return `IngestResult(text=<text>, extraction_method="pdf_text", ocr_confidence=None, readable=True)`.
3. Otherwise call `rasterize_and_ocr_pdf(doc)` → `(text, confidence)`. If `text.strip()` is empty, return `IngestResult(text="", extraction_method="ocr", ocr_confidence=confidence, readable=False)`. Else return `IngestResult(text=text, extraction_method="ocr", ocr_confidence=confidence, readable=True)`.
4. `.png`/`.jpg`/`.jpeg` → call `ocr_image(file_bytes)` inside `try/except`; on exception, return `IngestResult(text="", extraction_method=None, ocr_confidence=None, readable=False)`. On success, if `text.strip()` empty → `readable=False`, else `readable=True`; always `extraction_method="ocr"`.
5. Any other extension → `IngestResult(text="", extraction_method=None, ocr_confidence=None, readable=False)`.

- [ ] **Step 1: Write the failing tests**

Create `backend/app/pipeline/__init__.py` (empty).

```python
# backend/tests/test_ingest.py
import io

import fitz
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
    assert result.readable is False


def test_unsupported_extension_returns_unreadable():
    result = ingest_document(b"not a real file", "invoice.txt")
    assert result.readable is False
    assert result.extraction_method is None


def test_corrupt_pdf_bytes_returns_unreadable():
    result = ingest_document(b"this is not a pdf", "broken.pdf")
    assert result.readable is False
    assert result.extraction_method is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ingest.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.pipeline.ingest'`).

- [ ] **Step 3: Write `ingest.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ingest.py -v`
Expected: 6 passed.

If Tesseract binary is not found (`TesseractNotFoundError`), install it before proceeding — see Task 8 README step for install instructions; do not skip or mock around this, the pipeline requires a real Tesseract install.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/__init__.py backend/app/pipeline/ingest.py backend/tests/test_ingest.py
git commit -m "feat(backend): add ingest stage (PDF text + OCR)"
```

---

## Task 4: Field extraction stage (`extract_fields.py`)

**Files:**
- Create: `backend/app/pipeline/extract_fields.py`
- Test: `backend/tests/test_extract_fields.py`

**Interfaces:**
- Consumes: `app.models.invoice.InvoiceData`, `app.models.invoice.LineItem`, `app.models.invoice.FieldConfidence`, `app.config.CUIT_PATTERN`, `app.config.CAE_PATTERN`, `app.config.DATE_PATTERN`.
- Produces (used by `validate.py` and `main.py`):
  - `class FieldExtractionResult(NamedTuple): data: InvoiceData; field_confidence: dict[str, FieldConfidence]; items_parsed: bool`
  - `def extract_fields(text: str) -> FieldExtractionResult` — the single entry point for this stage.

Internal helper functions (private, but their existence matters for how `extract_fields` composes; write them as plain functions in the same file):
- `_find_tipo_comprobante(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — regex for `FACTURA\s+([ABC])\b` (case-insensitive) → high confidence; else search for a standalone `\b([ABC])\b` near the word `COD` → medium confidence; else `(None, None)`.
- `_find_punto_venta(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — regex `(?:Pto\.?\s*Vta\.?|P\.V\.)\s*:?\s*(\d{4,5})` case-insensitive → high; else `(None, None)`.
- `_find_numero_comprobante(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — regex `(?:Comp\.?\s*Nro\.?|N[°º]?)\s*:?\s*(\d{8})` case-insensitive → high; else `(None, None)`.
- `_find_fecha_emision(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — regex `Fecha\s+de\s+Emisi[oó]n\s*:?\s*(\d{2}/\d{2}/\d{4})` case-insensitive → high confidence, convert `DD/MM/YYYY` to ISO `YYYY-MM-DD`; else fallback: first standalone date pattern (`config.DATE_PATTERN`) anywhere in text → medium confidence, same conversion; else `(None, None)`. Date conversion: split on `/`, reassemble as `f"{yyyy}-{mm}-{dd}"`; if conversion raises, treat as no match.
- `_find_cuit_emisor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — take the text up to the halfway point by character count (`text[:len(text)//2]`), search `config.CUIT_PATTERN` there → high confidence if found in that half; else search the full text → medium confidence; else `(None, None)`.
- `_find_cuit_receptor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — search `config.CUIT_PATTERN` in `text[len(text)//2:]` (second half) → high; else `(None, None)`. (If both `_find_cuit_emisor` and `_find_cuit_receptor` would resolve to the exact same matched string, treat receptor as not found — this avoids the same CUIT being reported as both emisor and receptor from a single-CUIT document.)
- `_find_razon_social_emisor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — take the line immediately before the first CUIT match found by `_find_cuit_emisor`'s pattern search (split text on `\n`, find the line containing the matched CUIT, return the previous non-empty line stripped) → medium confidence; else `(None, None)`.
- `_find_razon_social_receptor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — regex `(?:Apellido\s+y\s+Nombre|Raz[oó]n\s+Social)\s*:?\s*([^\n]+)` case-insensitive → high confidence, strip result; else `(None, None)`.
- `_find_condicion_iva_receptor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — search (case-insensitive) for first occurrence of any of `["Responsable Inscripto", "Consumidor Final", "Monotributista", "Exento"]` in `text`; return the matched canonical string → high confidence; else `(None, None)`.
- `_find_cae(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — regex `CAE\s*N?[°º]?\s*:?\s*(\d{14})` case-insensitive → high; else `(None, None)`.
- `_find_vencimiento_cae(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]` — regex `Fecha\s+de\s+Vto\.?\s+de\s+CAE\s*:?\s*(\d{2}/\d{2}/\d{4})` case-insensitive → high confidence, ISO-convert (same logic as `_find_fecha_emision`); else `(None, None)`.
- `_find_moneda(text: str) -> tuple[str, FieldConfidence]` — if `"US$"` or `"USD"` present (case-insensitive) → `("USD", "high")`; else `("ARS", "high")` (default always has a value, so always high confidence — this field is never `None`).
- `_find_amount_near_label(text: str, label_pattern: str) -> tuple[Optional[float], Optional[FieldConfidence]]` — shared helper for `subtotal`, `iva`, `total`: regex `{label_pattern}\s*:?\s*\$?\s*([\d.,]+)` case-insensitive, take the **last** match in the text (per spec 4.2 note on `total`), parse amount string by removing thousands separators (`.`) and converting decimal comma to dot when the string matches Argentine format `\d{1,3}(\.\d{3})*,\d{2}` — otherwise parse as a plain float after stripping thousands commas. Confidence: `"high"` if `$` symbol was present adjacent to the number, else `"medium"`. On parse failure or no match → `(None, None)`.
  - `subtotal` uses `label_pattern = r"Subtotal"`.
  - `iva` uses `label_pattern = r"IVA"`.
  - `total` uses `label_pattern = r"Total"`.
- `_parse_items(text: str) -> tuple[list[LineItem], bool]` — find the substring between a table header match (regex `Cantidad\s+Descripci[oó]n.*?Subtotal`, case-insensitive, `re.DOTALL`) and the first occurrence of `"Subtotal"` after that header (search starting right after the header match). If no header match, return `([], False)`. Within that substring, split into lines; for each non-empty line, attempt regex `^(\d+(?:[.,]\d+)?)\s+(.+?)\s+([\d.,]+)\s+([\d.,]+)\s*$` capturing `cantidad, descripcion, precio_unitario, subtotal_linea`. Parse each numeric group with the same Argentine/plain amount parsing logic as `_find_amount_near_label`. Lines that don't match the pattern are skipped (not an error — just not a parseable item line). If at least one item line matched, return `(items, True)`; if the header was found but zero lines matched, return `([], False)`.

`extract_fields(text: str) -> FieldExtractionResult` composes all the `_find_*` helpers, builds an `InvoiceData` instance (using `moneda` default from `_find_moneda`), builds the `field_confidence` dict (only including keys where confidence is not `None`), calls `_parse_items` for `items`, and returns `FieldExtractionResult(data=..., field_confidence=..., items_parsed=<bool from _parse_items>)`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_extract_fields.py
from app.pipeline.extract_fields import extract_fields

SAMPLE_TEXT = """
Ejemplo SRL
CUIT: 20-12345678-9
FACTURA A
COD. 001
Pto. Vta.: 0003  Comp. Nro: 00012345
Fecha de Emisión: 15/03/2026

Apellido y Nombre / Razón Social: Cliente Ejemplo
CUIT: 27-98765432-1
Responsable Inscripto

Cantidad Descripción Precio Unit. Subtotal
1 Servicio de consultoría 10000,00 10000,00

Subtotal: $ 10000,00
IVA: $ 2100,00
Total: $ 12100,00

CAE N°: 12345678901234
Fecha de Vto. de CAE: 25/03/2026
"""


def test_extracts_full_header_with_high_confidence():
    result = extract_fields(SAMPLE_TEXT)
    assert result.data.tipo_comprobante == "A"
    assert result.data.punto_venta == "0003"
    assert result.data.numero_comprobante == "00012345"
    assert result.data.fecha_emision == "2026-03-15"
    assert result.data.cuit_emisor == "20-12345678-9"
    assert result.data.cuit_receptor == "27-98765432-1"
    assert result.data.razon_social_receptor == "Cliente Ejemplo"
    assert result.data.condicion_iva_receptor == "Responsable Inscripto"
    assert result.data.cae == "12345678901234"
    assert result.data.vencimiento_cae == "2026-03-25"
    assert result.data.moneda == "ARS"
    assert result.data.subtotal == 10000.0
    assert result.data.iva == 2100.0
    assert result.data.total == 12100.0
    assert result.field_confidence["tipo_comprobante"] == "high"


def test_parses_items_table():
    result = extract_fields(SAMPLE_TEXT)
    assert result.items_parsed is True
    assert len(result.data.items) == 1
    assert result.data.items[0].descripcion == "Servicio de consultoría"
    assert result.data.items[0].cantidad == 1.0
    assert result.data.items[0].subtotal_linea == 10000.0


def test_missing_fields_return_none_not_guessed():
    result = extract_fields("texto sin ningun campo reconocible")
    assert result.data.total is None
    assert result.data.cuit_emisor is None
    assert "total" not in result.field_confidence
    assert result.items_parsed is False
    assert result.data.items == []


def test_usd_currency_detected():
    text = "Total: US$ 500,00"
    result = extract_fields(text)
    assert result.data.moneda == "USD"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_extract_fields.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write `extract_fields.py`**

```python
# backend/app/pipeline/extract_fields.py
import re
from typing import NamedTuple, Optional

from app.config import CAE_PATTERN, CUIT_PATTERN, DATE_PATTERN
from app.models.invoice import FieldConfidence, InvoiceData, LineItem


class FieldExtractionResult(NamedTuple):
    data: InvoiceData
    field_confidence: dict[str, FieldConfidence]
    items_parsed: bool


def _parse_amount(raw: str) -> Optional[float]:
    raw = raw.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})*,\d{2}", raw):
        normalized = raw.replace(".", "").replace(",", ".")
    else:
        normalized = raw.replace(",", "")
    try:
        return float(normalized)
    except ValueError:
        return None


def _to_iso_date(ddmmyyyy: str) -> Optional[str]:
    parts = ddmmyyyy.split("/")
    if len(parts) != 3:
        return None
    dd, mm, yyyy = parts
    try:
        int(dd), int(mm), int(yyyy)
    except ValueError:
        return None
    return f"{yyyy}-{mm}-{dd}"


def _find_tipo_comprobante(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    match = re.search(r"FACTURA\s+([ABC])\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper(), "high"
    match = re.search(r"COD\.?\s*\d*\s*([ABC])\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper(), "medium"
    return None, None


def _find_punto_venta(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    match = re.search(r"(?:Pto\.?\s*Vta\.?|P\.V\.)\s*:?\s*(\d{4,5})", text, re.IGNORECASE)
    if match:
        return match.group(1), "high"
    return None, None


def _find_numero_comprobante(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    match = re.search(r"(?:Comp\.?\s*Nro\.?|N[°º]?)\s*:?\s*(\d{8})", text, re.IGNORECASE)
    if match:
        return match.group(1), "high"
    return None, None


def _find_fecha_emision(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    match = re.search(r"Fecha\s+de\s+Emisi[oó]n\s*:?\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if match:
        iso = _to_iso_date(match.group(1))
        if iso:
            return iso, "high"
    match = re.search(DATE_PATTERN, text)
    if match:
        iso = _to_iso_date(match.group(0))
        if iso:
            return iso, "medium"
    return None, None


def _find_cuit_emisor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    half = text[: len(text) // 2]
    match = re.search(CUIT_PATTERN, half)
    if match:
        return match.group(0), "high"
    match = re.search(CUIT_PATTERN, text)
    if match:
        return match.group(0), "medium"
    return None, None


def _find_cuit_receptor(text: str, cuit_emisor: Optional[str]) -> tuple[Optional[str], Optional[FieldConfidence]]:
    second_half = text[len(text) // 2 :]
    match = re.search(CUIT_PATTERN, second_half)
    if match and match.group(0) != cuit_emisor:
        return match.group(0), "high"
    return None, None


def _find_razon_social_emisor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    match = re.search(CUIT_PATTERN, text)
    if not match:
        return None, None
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if match.group(0) in line:
            for prev in reversed(lines[:i]):
                if prev.strip():
                    return prev.strip(), "medium"
            break
    return None, None


def _find_razon_social_receptor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    match = re.search(r"(?:Apellido\s+y\s+Nombre|Raz[oó]n\s+Social)\s*:?\s*([^\n]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip(), "high"
    return None, None


def _find_condicion_iva_receptor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    for label in ["Responsable Inscripto", "Consumidor Final", "Monotributista", "Exento"]:
        if re.search(re.escape(label), text, re.IGNORECASE):
            return label, "high"
    return None, None


def _find_cae(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    match = re.search(r"CAE\s*N?[°º]?\s*:?\s*(\d{14})", text, re.IGNORECASE)
    if match:
        return match.group(1), "high"
    return None, None


def _find_vencimiento_cae(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    match = re.search(r"Fecha\s+de\s+Vto\.?\s+de\s+CAE\s*:?\s*(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
    if match:
        iso = _to_iso_date(match.group(1))
        if iso:
            return iso, "high"
    return None, None


def _find_moneda(text: str) -> tuple[str, FieldConfidence]:
    if re.search(r"US\$|USD", text, re.IGNORECASE):
        return "USD", "high"
    return "ARS", "high"


def _find_amount_near_label(text: str, label_pattern: str) -> tuple[Optional[float], Optional[FieldConfidence]]:
    pattern = rf"{label_pattern}\s*:?\s*(\$?)\s*([\d.,]+)"
    matches = list(re.finditer(pattern, text, re.IGNORECASE))
    if not matches:
        return None, None
    last = matches[-1]
    amount = _parse_amount(last.group(2))
    if amount is None:
        return None, None
    confidence: FieldConfidence = "high" if last.group(1) == "$" else "medium"
    return amount, confidence


def _parse_items(text: str) -> tuple[list[LineItem], bool]:
    header_match = re.search(r"Cantidad\s+Descripci[oó]n.*?Subtotal", text, re.IGNORECASE | re.DOTALL)
    if not header_match:
        return [], False

    remainder = text[header_match.end() :]
    stop_match = re.search(r"Subtotal", remainder, re.IGNORECASE)
    table_text = remainder[: stop_match.start()] if stop_match else remainder

    line_pattern = re.compile(r"^(\d+(?:[.,]\d+)?)\s+(.+?)\s+([\d.,]+)\s+([\d.,]+)\s*$")
    items: list[LineItem] = []
    for line in table_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = line_pattern.match(line)
        if not match:
            continue
        cantidad = _parse_amount(match.group(1))
        precio_unitario = _parse_amount(match.group(3))
        subtotal_linea = _parse_amount(match.group(4))
        if cantidad is None or precio_unitario is None or subtotal_linea is None:
            continue
        items.append(
            LineItem(
                descripcion=match.group(2).strip(),
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                subtotal_linea=subtotal_linea,
            )
        )

    return items, len(items) > 0


def extract_fields(text: str) -> FieldExtractionResult:
    field_confidence: dict[str, FieldConfidence] = {}

    def record(name: str, value_confidence: tuple):
        value, confidence = value_confidence
        if confidence is not None:
            field_confidence[name] = confidence
        return value

    tipo_comprobante = record("tipo_comprobante", _find_tipo_comprobante(text))
    punto_venta = record("punto_venta", _find_punto_venta(text))
    numero_comprobante = record("numero_comprobante", _find_numero_comprobante(text))
    fecha_emision = record("fecha_emision", _find_fecha_emision(text))
    cuit_emisor = record("cuit_emisor", _find_cuit_emisor(text))
    cuit_receptor = record("cuit_receptor", _find_cuit_receptor(text, cuit_emisor))
    razon_social_emisor = record("razon_social_emisor", _find_razon_social_emisor(text))
    razon_social_receptor = record("razon_social_receptor", _find_razon_social_receptor(text))
    condicion_iva_receptor = record("condicion_iva_receptor", _find_condicion_iva_receptor(text))
    cae = record("cae", _find_cae(text))
    vencimiento_cae = record("vencimiento_cae", _find_vencimiento_cae(text))
    moneda = record("moneda", _find_moneda(text))
    subtotal = record("subtotal", _find_amount_near_label(text, r"Subtotal"))
    iva = record("iva", _find_amount_near_label(text, r"IVA"))
    total = record("total", _find_amount_near_label(text, r"Total"))
    items, items_parsed = _parse_items(text)

    data = InvoiceData(
        tipo_comprobante=tipo_comprobante,
        punto_venta=punto_venta,
        numero_comprobante=numero_comprobante,
        fecha_emision=fecha_emision,
        cuit_emisor=cuit_emisor,
        razon_social_emisor=razon_social_emisor,
        cuit_receptor=cuit_receptor,
        razon_social_receptor=razon_social_receptor,
        condicion_iva_receptor=condicion_iva_receptor,
        cae=cae,
        vencimiento_cae=vencimiento_cae,
        moneda=moneda,
        subtotal=subtotal,
        iva=iva,
        total=total,
        items=items,
    )

    return FieldExtractionResult(data=data, field_confidence=field_confidence, items_parsed=items_parsed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extract_fields.py -v`
Expected: 4 passed.

If `test_extracts_full_header_with_high_confidence` fails on a specific field, debug that single regex against `SAMPLE_TEXT` in a Python shell before changing unrelated code — do not loosen unrelated patterns to force a pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/extract_fields.py backend/tests/test_extract_fields.py
git commit -m "feat(backend): add regex-based field extraction stage"
```

---

## Task 5: Validation stage (`validate.py`)

**Files:**
- Create: `backend/app/pipeline/validate.py`
- Test: `backend/tests/test_validate.py` (extend the file created in Task 1)

**Interfaces:**
- Consumes: `app.models.invoice.{InvoiceData, ExtractionResult, Warning, ErrorDetail}`, `app.pipeline.ingest.IngestResult`, `app.pipeline.extract_fields.FieldExtractionResult`, `app.config.{REQUIRED_HEADER_FIELDS, AMOUNT_TOLERANCE_RATIO, LOW_OCR_CONFIDENCE_THRESHOLD, CUIT_PATTERN, CAE_PATTERN}`.
- Produces (used by `main.py`):
  - `def build_extraction_result(ingest_result: "IngestResult", field_result: Optional["FieldExtractionResult"]) -> ExtractionResult` — the single entry point. `field_result` is `None` when ingest failed (`ingest_result.readable is False`).

Behavior:
1. If `ingest_result.readable is False`: return `ExtractionResult(status="failed", extraction_method=ingest_result.extraction_method, ocr_confidence=ingest_result.ocr_confidence, data=InvoiceData(), field_confidence={}, warnings=[], errors=[ErrorDetail(code="UNREADABLE_DOCUMENT", field=None, message="No se pudo extraer texto legible del documento.")])`.
2. Otherwise, start `warnings: list[Warning] = []`.
3. **Format validation** (only runs on non-`None` values, appends to `warnings` with code `INVALID_FORMAT` and the field name; does NOT null out the field — it stays as extracted, but is flagged):
   - `cuit_emisor` / `cuit_receptor`: if present, must fully match `CUIT_PATTERN` (`re.fullmatch`); additionally must pass the AFIP CUIT check-digit algorithm (implement `_is_valid_cuit_checksum(cuit: str) -> bool` using the standard AFIP multiplier sequence `[5,4,3,2,7,6,5,4,3,2]` over the 10 digits excluding dashes, verification digit is the 11th digit — `remainder = 11 - (sum(digit*mult) % 11)`; valid digit is `0` if `remainder == 11`, `remainder` if `remainder < 10`, else the CUIT is invalid). If format doesn't match pattern or checksum fails → append warning.
   - `cae`: if present, must fully match `CAE_PATTERN`. If not → append warning.
   - `fecha_emision` / `vencimiento_cae`: if present, must be parseable via `datetime.date.fromisoformat`. If not → append warning.
   - `subtotal` / `iva` / `total` / item `precio_unitario` / item `subtotal_linea`: if present, must be `>= 0`. If negative → append warning.
4. **Obligatoriedad:** for each `field in REQUIRED_HEADER_FIELDS`, if `getattr(data, field) is None`, append `Warning(code="MISSING_REQUIRED_FIELD", field=field, message=f"No se pudo detectar el campo obligatorio '{field}'.")`.
5. **Items parsed:** if `field_result.items_parsed is False`, append `Warning(code="ITEMS_NOT_PARSED", field="items", message="No se pudo segmentar la tabla de items de forma confiable.")`.
6. **Consistency — items vs subtotal:** if `data.items` is non-empty and `data.subtotal is not None`: compute `items_sum = sum(item.subtotal_linea for item in data.items)`; if `abs(items_sum - data.subtotal) > data.subtotal * AMOUNT_TOLERANCE_RATIO` (guard against `data.subtotal == 0` by using `abs(items_sum - data.subtotal) > max(abs(data.subtotal), 1.0) * AMOUNT_TOLERANCE_RATIO`), append `Warning(code="ITEMS_SUBTOTAL_MISMATCH", field="items", message="La suma de las líneas de detalle no coincide con el subtotal.")`.
7. **Consistency — total:** if `data.subtotal is not None and data.iva is not None and data.total is not None`: compute `expected_total = data.subtotal + data.iva`; if `abs(expected_total - data.total) > max(abs(data.total), 1.0) * AMOUNT_TOLERANCE_RATIO`, append `Warning(code="TOTAL_MISMATCH", field="total", message="Subtotal + IVA no coincide con el total.")`.
8. **OCR confidence:** if `ingest_result.extraction_method == "ocr"` and `ingest_result.ocr_confidence is not None` and `ingest_result.ocr_confidence < LOW_OCR_CONFIDENCE_THRESHOLD`, append `Warning(code="LOW_OCR_CONFIDENCE", field=None, message=f"Confianza promedio de OCR baja ({ingest_result.ocr_confidence:.1f}%).")`.
9. **Status determination:**
   - Compute `missing_critical = any(getattr(data, f) is None for f in ["numero_comprobante", "total"])` (the two fields the spec calls out in 4.4 as making a document "not processable" — no comprobante number and no total means nothing usable was extracted).
   - If `missing_critical`: `status = "failed"`, and add `ErrorDetail(code="CRITICAL_FIELDS_MISSING", field=None, message="No se pudo extraer el número de comprobante ni el total del documento.")` to `errors`.
   - Elif `warnings` is non-empty: `status = "partial"`.
   - Else: `status = "ok"`.
10. Return `ExtractionResult(status=status, extraction_method=ingest_result.extraction_method, ocr_confidence=ingest_result.ocr_confidence, data=field_result.data, field_confidence=field_result.field_confidence, warnings=warnings, errors=errors)`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_validate.py`:

```python
# --- validate.py tests (appended) ---
from app.pipeline.extract_fields import FieldExtractionResult
from app.pipeline.ingest import IngestResult
from app.pipeline.validate import build_extraction_result


def _field_result(**overrides) -> FieldExtractionResult:
    base = InvoiceData(
        tipo_comprobante="A",
        punto_venta="0003",
        numero_comprobante="00012345",
        fecha_emision="2026-03-15",
        cuit_emisor="20-12345678-9",
        razon_social_emisor="Ejemplo SRL",
        subtotal=10000.0,
        iva=2100.0,
        total=12100.0,
        items=[
            LineItem(descripcion="Item 1", cantidad=1, precio_unitario=10000.0, subtotal_linea=10000.0)
        ],
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return FieldExtractionResult(data=base, field_confidence={"tipo_comprobante": "high"}, items_parsed=True)


def test_unreadable_document_returns_failed_with_error():
    ingest_result = IngestResult(text="", extraction_method=None, ocr_confidence=None, readable=False)
    result = build_extraction_result(ingest_result, None)
    assert result.status == "failed"
    assert result.errors[0].code == "UNREADABLE_DOCUMENT"


def test_clean_invoice_returns_ok():
    ingest_result = IngestResult(text="...", extraction_method="pdf_text", ocr_confidence=None, readable=True)
    field_result = _field_result()
    result = build_extraction_result(ingest_result, field_result)
    assert result.status == "ok"
    assert result.warnings == []


def test_missing_optional_field_returns_partial_with_warning():
    ingest_result = IngestResult(text="...", extraction_method="pdf_text", ocr_confidence=None, readable=True)
    field_result = _field_result(cuit_receptor=None)
    result = build_extraction_result(ingest_result, field_result)
    assert result.status == "partial"
    codes = [w.code for w in result.warnings]
    assert "MISSING_REQUIRED_FIELD" not in codes  # cuit_receptor is not required


def test_missing_required_field_returns_partial_with_missing_warning():
    ingest_result = IngestResult(text="...", extraction_method="pdf_text", ocr_confidence=None, readable=True)
    field_result = _field_result(subtotal=None)
    result = build_extraction_result(ingest_result, field_result)
    assert result.status == "partial"
    warning = next(w for w in result.warnings if w.code == "MISSING_REQUIRED_FIELD")
    assert warning.field == "subtotal"


def test_missing_total_and_numero_is_failed():
    ingest_result = IngestResult(text="...", extraction_method="pdf_text", ocr_confidence=None, readable=True)
    field_result = _field_result(total=None, numero_comprobante=None)
    result = build_extraction_result(ingest_result, field_result)
    assert result.status == "failed"
    assert any(e.code == "CRITICAL_FIELDS_MISSING" for e in result.errors)


def test_items_subtotal_mismatch_detected():
    ingest_result = IngestResult(text="...", extraction_method="pdf_text", ocr_confidence=None, readable=True)
    field_result = _field_result(
        items=[LineItem(descripcion="Item 1", cantidad=1, precio_unitario=1.0, subtotal_linea=1.0)]
    )
    result = build_extraction_result(ingest_result, field_result)
    assert any(w.code == "ITEMS_SUBTOTAL_MISMATCH" for w in result.warnings)


def test_total_mismatch_detected():
    ingest_result = IngestResult(text="...", extraction_method="pdf_text", ocr_confidence=None, readable=True)
    field_result = _field_result(total=99999.0)
    result = build_extraction_result(ingest_result, field_result)
    assert any(w.code == "TOTAL_MISMATCH" for w in result.warnings)


def test_low_ocr_confidence_adds_warning():
    ingest_result = IngestResult(text="...", extraction_method="ocr", ocr_confidence=15.0, readable=True)
    field_result = _field_result()
    result = build_extraction_result(ingest_result, field_result)
    assert any(w.code == "LOW_OCR_CONFIDENCE" for w in result.warnings)


def test_items_not_parsed_adds_warning():
    ingest_result = IngestResult(text="...", extraction_method="pdf_text", ocr_confidence=None, readable=True)
    field_result = _field_result(items=[])
    field_result = field_result._replace(items_parsed=False)
    result = build_extraction_result(ingest_result, field_result)
    assert any(w.code == "ITEMS_NOT_PARSED" for w in result.warnings)


def test_invalid_cuit_checksum_adds_format_warning():
    ingest_result = IngestResult(text="...", extraction_method="pdf_text", ocr_confidence=None, readable=True)
    field_result = _field_result(cuit_emisor="20-11111111-1")
    result = build_extraction_result(ingest_result, field_result)
    assert any(w.code == "INVALID_FORMAT" and w.field == "cuit_emisor" for w in result.warnings)
```

Note: `_field_result` mutates a shared `InvoiceData` instance via `setattr` for overrides — since `items` is a list default, passing `items=[]` as an override works correctly with `setattr` too (it replaces the whole list).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_validate.py -v`
Expected: the new tests FAIL (`ModuleNotFoundError: No module named 'app.pipeline.validate'`); the two original model tests still pass.

- [ ] **Step 3: Write `validate.py`**

```python
# backend/app/pipeline/validate.py
import re
from datetime import date
from typing import Optional

from app.config import (
    AMOUNT_TOLERANCE_RATIO,
    CAE_PATTERN,
    CUIT_PATTERN,
    LOW_OCR_CONFIDENCE_THRESHOLD,
    REQUIRED_HEADER_FIELDS,
)
from app.models.invoice import ErrorDetail, ExtractionResult, InvoiceData, Warning
from app.pipeline.extract_fields import FieldExtractionResult
from app.pipeline.ingest import IngestResult

_CUIT_MULTIPLIERS = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]


def _is_valid_cuit_checksum(cuit: str) -> bool:
    digits = cuit.replace("-", "")
    if len(digits) != 11 or not digits.isdigit():
        return False
    base_digits = [int(d) for d in digits[:10]]
    check_digit = int(digits[10])
    total = sum(d * m for d, m in zip(base_digits, _CUIT_MULTIPLIERS))
    remainder = 11 - (total % 11)
    if remainder == 11:
        expected = 0
    elif remainder == 10:
        return False
    else:
        expected = remainder
    return expected == check_digit


def _validate_format(data: InvoiceData, warnings: list[Warning]) -> None:
    for field_name in ("cuit_emisor", "cuit_receptor"):
        value = getattr(data, field_name)
        if value is not None and (not re.fullmatch(CUIT_PATTERN, value) or not _is_valid_cuit_checksum(value)):
            warnings.append(Warning(code="INVALID_FORMAT", field=field_name, message=f"CUIT inválido en '{field_name}'."))

    if data.cae is not None and not re.fullmatch(CAE_PATTERN, data.cae):
        warnings.append(Warning(code="INVALID_FORMAT", field="cae", message="CAE con formato inválido."))

    for field_name in ("fecha_emision", "vencimiento_cae"):
        value = getattr(data, field_name)
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError:
                warnings.append(Warning(code="INVALID_FORMAT", field=field_name, message=f"Fecha inválida en '{field_name}'."))

    for field_name in ("subtotal", "iva", "total"):
        value = getattr(data, field_name)
        if value is not None and value < 0:
            warnings.append(Warning(code="INVALID_FORMAT", field=field_name, message=f"Monto negativo en '{field_name}'."))

    for idx, item in enumerate(data.items):
        if item.precio_unitario < 0 or item.subtotal_linea < 0:
            warnings.append(Warning(code="INVALID_FORMAT", field=f"items[{idx}]", message="Monto negativo en línea de detalle."))


def _validate_required_fields(data: InvoiceData, warnings: list[Warning]) -> None:
    for field_name in REQUIRED_HEADER_FIELDS:
        if getattr(data, field_name) is None:
            warnings.append(
                Warning(
                    code="MISSING_REQUIRED_FIELD",
                    field=field_name,
                    message=f"No se pudo detectar el campo obligatorio '{field_name}'.",
                )
            )


def _validate_consistency(data: InvoiceData, warnings: list[Warning]) -> None:
    if data.items and data.subtotal is not None:
        items_sum = sum(item.subtotal_linea for item in data.items)
        tolerance = max(abs(data.subtotal), 1.0) * AMOUNT_TOLERANCE_RATIO
        if abs(items_sum - data.subtotal) > tolerance:
            warnings.append(
                Warning(code="ITEMS_SUBTOTAL_MISMATCH", field="items", message="La suma de las líneas de detalle no coincide con el subtotal.")
            )

    if data.subtotal is not None and data.iva is not None and data.total is not None:
        expected_total = data.subtotal + data.iva
        tolerance = max(abs(data.total), 1.0) * AMOUNT_TOLERANCE_RATIO
        if abs(expected_total - data.total) > tolerance:
            warnings.append(Warning(code="TOTAL_MISMATCH", field="total", message="Subtotal + IVA no coincide con el total."))


def build_extraction_result(
    ingest_result: IngestResult, field_result: Optional[FieldExtractionResult]
) -> ExtractionResult:
    if not ingest_result.readable or field_result is None:
        return ExtractionResult(
            status="failed",
            extraction_method=ingest_result.extraction_method,
            ocr_confidence=ingest_result.ocr_confidence,
            data=InvoiceData(),
            field_confidence={},
            warnings=[],
            errors=[ErrorDetail(code="UNREADABLE_DOCUMENT", field=None, message="No se pudo extraer texto legible del documento.")],
        )

    data = field_result.data
    warnings: list[Warning] = []
    errors: list[ErrorDetail] = []

    _validate_format(data, warnings)
    _validate_required_fields(data, warnings)

    if not field_result.items_parsed:
        warnings.append(Warning(code="ITEMS_NOT_PARSED", field="items", message="No se pudo segmentar la tabla de items de forma confiable."))

    _validate_consistency(data, warnings)

    if (
        ingest_result.extraction_method == "ocr"
        and ingest_result.ocr_confidence is not None
        and ingest_result.ocr_confidence < LOW_OCR_CONFIDENCE_THRESHOLD
    ):
        warnings.append(
            Warning(code="LOW_OCR_CONFIDENCE", field=None, message=f"Confianza promedio de OCR baja ({ingest_result.ocr_confidence:.1f}%).")
        )

    missing_critical = data.numero_comprobante is None or data.total is None
    if missing_critical:
        status = "failed"
        errors.append(
            ErrorDetail(code="CRITICAL_FIELDS_MISSING", field=None, message="No se pudo extraer el número de comprobante ni el total del documento.")
        )
    elif warnings:
        status = "partial"
    else:
        status = "ok"

    return ExtractionResult(
        status=status,
        extraction_method=ingest_result.extraction_method,
        ocr_confidence=ingest_result.ocr_confidence,
        data=data,
        field_confidence=field_result.field_confidence,
        warnings=warnings,
        errors=errors,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_validate.py -v`
Expected: all tests pass (2 from Task 1 + 10 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/validate.py backend/tests/test_validate.py
git commit -m "feat(backend): add validation stage with consistency and CUIT checksum checks"
```

---

## Task 6: Synthetic test fixtures

**Files:**
- Create: `backend/tests/fixtures/generate_fixtures.py` (throwaway generator script, run once, kept in repo for reproducibility)
- Create (generated by the script): `backend/tests/fixtures/synthetic_clean.pdf`, `backend/tests/fixtures/synthetic_low_confidence.png`, `backend/tests/fixtures/synthetic_mismatch.pdf`, `backend/tests/fixtures/synthetic_unreadable.png`
- Create: `backend/tests/fixtures/README.md`

**Interfaces:**
- Consumes: `fitz` (PyMuPDF), `PIL`.
- Produces: four fixture files on disk, consumed by Task 7's `test_integration.py`.

- [ ] **Step 1: Write the fixture generator script**

```python
# backend/tests/fixtures/generate_fixtures.py
"""Regenerate synthetic invoice fixtures used by test_integration.py.

Run manually with: python tests/fixtures/generate_fixtures.py
"""
import io
import os

import fitz
from PIL import Image, ImageDraw, ImageFilter

FIXTURES_DIR = os.path.dirname(__file__)

CLEAN_INVOICE_TEXT = """Ejemplo SRL
CUIT: 20-12345678-9
FACTURA A
COD. 001
Pto. Vta.: 0003  Comp. Nro: 00012345
Fecha de Emision: 15/03/2026

Apellido y Nombre / Razon Social: Cliente Ejemplo
CUIT: 27-98765432-8
Responsable Inscripto

Cantidad Descripcion Precio Unit. Subtotal
1 Servicio de consultoria 10000,00 10000,00

Subtotal: $ 10000,00
IVA: $ 2100,00
Total: $ 12100,00

CAE N: 12345678901234
Fecha de Vto. de CAE: 25/03/2026
"""

MISMATCH_INVOICE_TEXT = """Ejemplo SRL
CUIT: 20-12345678-9
FACTURA A
COD. 001
Pto. Vta.: 0003  Comp. Nro: 00099999
Fecha de Emision: 20/03/2026

Apellido y Nombre / Razon Social: Cliente Discrepante
CUIT: 27-98765432-8
Responsable Inscripto

Cantidad Descripcion Precio Unit. Subtotal
1 Producto con precio incorrecto 500,00 500,00

Subtotal: $ 10000,00
IVA: $ 2100,00
Total: $ 99999,00

CAE N: 98765432109876
Fecha de Vto. de CAE: 30/03/2026
"""


def _write_text_pdf(path: str, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((36, 36), text, fontsize=9)
    doc.save(path)
    doc.close()


def _write_low_confidence_image(path: str, text: str) -> None:
    img = Image.new("RGB", (600, 200), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((10, 80), text, fill=(180, 180, 180))
    img = img.filter(ImageFilter.GaussianBlur(radius=3))
    img.save(path)


def _write_blank_image(path: str) -> None:
    img = Image.new("RGB", (200, 200), color="white")
    img.save(path)


def main() -> None:
    _write_text_pdf(os.path.join(FIXTURES_DIR, "synthetic_clean.pdf"), CLEAN_INVOICE_TEXT)
    _write_text_pdf(os.path.join(FIXTURES_DIR, "synthetic_mismatch.pdf"), MISMATCH_INVOICE_TEXT)
    _write_low_confidence_image(
        os.path.join(FIXTURES_DIR, "synthetic_low_confidence.png"), "TOTAL 500"
    )
    _write_blank_image(os.path.join(FIXTURES_DIR, "synthetic_unreadable.png"))
    print("Fixtures generated in", FIXTURES_DIR)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the generator**

From `backend/`, with venv active:

```bash
python tests/fixtures/generate_fixtures.py
```

Expected output: `Fixtures generated in .../backend/tests/fixtures`, and the four files listed above now exist in that directory.

- [ ] **Step 3: Write the fixtures README**

```markdown
# Fixtures de prueba

## Sintéticas (generadas)

Generadas por `generate_fixtures.py`. Para regenerarlas:

```bash
python tests/fixtures/generate_fixtures.py
```

- `synthetic_clean.pdf` — PDF con texto embebido, factura completa y consistente (camino feliz, `status: ok`).
- `synthetic_mismatch.pdf` — PDF con texto embebido, pero con inconsistencia matemática deliberada entre subtotal/IVA/total (`status: partial`, warning `TOTAL_MISMATCH`).
- `synthetic_low_confidence.png` — imagen con texto borroso de baja calidad, para forzar confianza OCR baja (`status: partial`, warning `LOW_OCR_CONFIDENCE`).
- `synthetic_unreadable.png` — imagen en blanco sin texto, documento no procesable (`status: failed`).

## Reales anonimizadas

Cuando el usuario provea facturas ARCA/AFIP reales anonimizadas, agregarlas a esta
carpeta con un nombre descriptivo (ej. `real_factura_a_01.pdf`). Antes de commitear,
verificar que no contengan CUIT, razón social, ni datos personales reales sin
anonimizar — reemplazar por valores ficticios si es necesario.
```

- [ ] **Step 4: Verify fixtures load correctly**

Run (from `backend/`, venv active):

```bash
python -c "import fitz; d = fitz.open('tests/fixtures/synthetic_clean.pdf'); print(len(d[0].get_text()) > 20)"
```

Expected: `True`.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures/generate_fixtures.py backend/tests/fixtures/README.md backend/tests/fixtures/synthetic_clean.pdf backend/tests/fixtures/synthetic_low_confidence.png backend/tests/fixtures/synthetic_mismatch.pdf backend/tests/fixtures/synthetic_unreadable.png
git commit -m "test(backend): add synthetic invoice fixtures for integration tests"
```

---

## Task 7: FastAPI app + integration tests

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/tests/test_integration.py`

**Interfaces:**
- Consumes: `app.pipeline.ingest.ingest_document`, `app.pipeline.extract_fields.extract_fields`, `app.pipeline.validate.build_extraction_result`, `app.models.invoice.ExtractionResult`.
- Produces: running FastAPI app object `app` in `app.main`, importable by `uvicorn app.main:app` and by `httpx`/`TestClient` in tests. Route: `POST /extract`.

`main.py` behavior:
1. Create `FastAPI()` instance named `app`.
2. Add `CORSMiddleware` allowing origin `http://localhost:3000`, all methods, all headers.
3. `POST /extract` accepts `file: UploadFile = File(...)`. Read bytes via `await file.read()`. If `file.filename` is falsy or bytes are empty, raise `HTTPException(status_code=400, detail="No se recibió ningún archivo.")`.
4. Call `ingest_document(file_bytes, file.filename)`.
5. If `ingest_result.readable` is `True`, call `extract_fields(ingest_result.text)` to get `field_result`; else `field_result = None`.
6. Call `build_extraction_result(ingest_result, field_result)` → `ExtractionResult`.
7. Return `result` directly (FastAPI serializes Pydantic models automatically) — always HTTP 200 for a successfully-run pipeline, per the Global Constraints.

- [ ] **Step 1: Write the failing integration tests**

```python
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
```

Note: `test_missing_file_returns_400` expects `422` as an acceptable alternative because FastAPI returns `422` automatically when the required `file` form field is absent entirely (before your handler code runs) — both are correct "malformed request" outcomes per the Global Constraints.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_integration.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.main'`).

- [ ] **Step 3: Write `main.py`**

```python
# backend/app/main.py
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.models.invoice import ExtractionResult
from app.pipeline.extract_fields import extract_fields
from app.pipeline.ingest import ingest_document
from app.pipeline.validate import build_extraction_result

app = FastAPI(title="Extractor de Facturas ARCA")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/extract", response_model=ExtractionResult)
async def extract(file: UploadFile = File(...)) -> ExtractionResult:
    file_bytes = await file.read()
    if not file.filename or not file_bytes:
        raise HTTPException(status_code=400, detail="No se recibió ningún archivo.")

    ingest_result = ingest_document(file_bytes, file.filename)

    field_result = extract_fields(ingest_result.text) if ingest_result.readable else None

    return build_extraction_result(ingest_result, field_result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_integration.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest -v`
Expected: all tests across `test_config.py`, `test_ingest.py`, `test_extract_fields.py`, `test_validate.py`, `test_integration.py` pass.

- [ ] **Step 6: Manually smoke-test the running server**

```bash
uvicorn app.main:app --reload --port 8000
```

In another terminal: `curl -F "file=@tests/fixtures/synthetic_clean.pdf" http://localhost:8000/extract`
Expected: JSON body with `"status": "ok"`. Stop the server (Ctrl+C) before continuing.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/tests/test_integration.py
git commit -m "feat(backend): add FastAPI POST /extract endpoint wiring the full pipeline"
```

---

## Task 8: Backend README

**Files:**
- Create: `backend/README.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: setup/run instructions consumed by a human evaluator and by the root README (Task 12) via a link.

- [ ] **Step 1: Write `backend/README.md`**

```markdown
# Backend — Extractor de Facturas ARCA

API FastAPI que recibe una factura (PDF o imagen) y devuelve datos estructurados
en JSON, con validación y manejo explícito de casos ambiguos o fallidos.

## Requisitos

- Python 3.11+
- Tesseract OCR instalado en el sistema (binario, no solo el paquete pip):
  - **Windows:** descargar el instalador desde
    https://github.com/UB-Mannheim/tesseract/wiki e instalar. Agregar la carpeta
    de instalación (ej. `C:\Program Files\Tesseract-OCR`) al PATH, o configurar
    `pytesseract.pytesseract.tesseract_cmd` apuntando al ejecutable.
  - **macOS:** `brew install tesseract`
  - **Linux (Debian/Ubuntu):** `sudo apt install tesseract-ocr`

## Setup

```bash
cd backend
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Correr el servidor

```bash
uvicorn app.main:app --reload --port 8000
```

La API queda disponible en `http://localhost:8000`, con documentación interactiva
(Swagger) en `http://localhost:8000/docs`.

## Probar el endpoint manualmente

```bash
curl -F "file=@tests/fixtures/synthetic_clean.pdf" http://localhost:8000/extract
```

## Tests

```bash
pytest -v
```

## Regenerar fixtures sintéticas

```bash
python tests/fixtures/generate_fixtures.py
```

## Estructura

- `app/pipeline/ingest.py` — detecta tipo de archivo, extrae texto de PDF o corre OCR.
- `app/pipeline/extract_fields.py` — reglas/regex para estructurar campos de factura ARCA.
- `app/pipeline/validate.py` — validación de formato, obligatoriedad y consistencia numérica.
- `app/models/invoice.py` — schemas Pydantic de request/response.
- `app/main.py` — endpoint `POST /extract`.
```

- [ ] **Step 2: Verify the documented commands actually work**

From a clean shell, re-run the Setup and Correr el servidor sections exactly as written (reuse the venv from Task 1 if already created — just confirm `pip install -r requirements.txt` is idempotent and the server starts without errors), then Ctrl+C to stop.

- [ ] **Step 3: Commit**

```bash
git add backend/README.md
git commit -m "docs(backend): add backend setup and usage instructions"
```

---

## Task 9: Frontend scaffolding + types + API client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.js`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/globals.css`
- Create: `frontend/lib/types.ts`
- Create: `frontend/lib/api.ts`
- Create: `frontend/.env.local.example`
- Create: `frontend/.gitignore`

**Interfaces:**
- Consumes: backend `ExtractionResult` JSON shape (spec Section 5).
- Produces (used by Tasks 10-11):
  - `frontend/lib/types.ts` exports: `LineItem`, `InvoiceData`, `Warning`, `ErrorDetail`, `ExtractionResult`, `FieldConfidence`, `ExtractionStatus`, `ExtractionMethod` — TypeScript interfaces mirroring the Pydantic models field-for-field (same field names, since the backend returns them verbatim).
  - `frontend/lib/api.ts` exports `async function extractInvoice(file: File): Promise<ExtractionResult>` — POSTs to `${process.env.NEXT_PUBLIC_API_URL}/extract` as `multipart/form-data`, throws an `Error` with a descriptive message on non-2xx or network failure, otherwise returns the parsed JSON cast to `ExtractionResult`.

- [ ] **Step 1: Initialize the Next.js project**

From the repo root:

```bash
npx create-next-app@latest frontend --typescript --app --no-tailwind --no-src-dir --import-alias "@/*" --eslint --use-npm
```

When prompted interactively (if not fully covered by flags), choose: no Tailwind (keep it minimal, plain CSS), App Router yes, `src/` directory no.

- [ ] **Step 2: Write `lib/types.ts`**

```typescript
// frontend/lib/types.ts
export type FieldConfidence = "high" | "medium" | "low";
export type ExtractionStatus = "ok" | "partial" | "failed";
export type ExtractionMethod = "pdf_text" | "ocr";

export interface LineItem {
  descripcion: string;
  cantidad: number;
  precio_unitario: number;
  subtotal_linea: number;
}

export interface InvoiceData {
  tipo_comprobante: string | null;
  punto_venta: string | null;
  numero_comprobante: string | null;
  fecha_emision: string | null;
  cuit_emisor: string | null;
  razon_social_emisor: string | null;
  cuit_receptor: string | null;
  razon_social_receptor: string | null;
  condicion_iva_receptor: string | null;
  cae: string | null;
  vencimiento_cae: string | null;
  moneda: string;
  subtotal: number | null;
  iva: number | null;
  total: number | null;
  items: LineItem[];
}

export interface Warning {
  code: string;
  field: string | null;
  message: string;
}

export interface ErrorDetail {
  code: string;
  field: string | null;
  message: string;
}

export interface ExtractionResult {
  status: ExtractionStatus;
  extraction_method: ExtractionMethod | null;
  ocr_confidence: number | null;
  data: InvoiceData;
  field_confidence: Record<string, FieldConfidence>;
  warnings: Warning[];
  errors: ErrorDetail[];
}
```

- [ ] **Step 3: Write `lib/api.ts`**

```typescript
// frontend/lib/api.ts
import type { ExtractionResult } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function extractInvoice(file: File): Promise<ExtractionResult> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_URL}/extract`, {
      method: "POST",
      body: formData,
    });
  } catch (err) {
    throw new Error("No se pudo conectar con el servidor. ¿Está corriendo el backend?");
  }

  if (!response.ok) {
    throw new Error(`Error del servidor (${response.status}): no se pudo procesar el archivo.`);
  }

  return (await response.json()) as ExtractionResult;
}
```

- [ ] **Step 4: Write `.env.local.example`**

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Copy it to `.env.local` for local dev: `cp .env.local.example .env.local` (or manually create on Windows).

- [ ] **Step 5: Verify the scaffold builds**

From `frontend/`:

```bash
npm run build
```

Expected: build succeeds (the default `create-next-app` page still exists at this point — that's fine, it's replaced in Task 10).

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/next.config.js frontend/app/layout.tsx frontend/app/globals.css frontend/lib/types.ts frontend/lib/api.ts frontend/.env.local.example frontend/.gitignore frontend/next-env.d.ts
git commit -m "chore(frontend): scaffold Next.js app with API client and types"
```

Confirm `frontend/.gitignore` (generated by `create-next-app`) already excludes `node_modules/`, `.next/`, and `.env.local` — if `.env.local` is not listed, add it before committing.

---

## Task 10: `UploadForm` and `ResultView` components

**Files:**
- Create: `frontend/components/UploadForm.tsx`
- Create: `frontend/components/ResultView.tsx`

**Interfaces:**
- Consumes: `frontend/lib/types.ts` (`ExtractionResult`), `frontend/lib/api.ts` (`extractInvoice`).
- Produces (used by Task 11's `page.tsx`):
  - `UploadForm` props: `{ onResult: (result: ExtractionResult, fileName: string) => void }`. Renders a file input (`accept="application/pdf,image/png,image/jpeg"`), a submit button labeled "Extraer", a loading state while the request is in flight, and an inline error message (from a thrown `Error`) if the call fails. On success, calls `onResult(result, file.name)` and does not itself render the result.
  - `ResultView` props: `{ result: ExtractionResult }`. Renders:
    - A status badge: green background + "OK" text for `"ok"`, amber + "Parcial" for `"partial"`, red + "Fallido" for `"failed"`.
    - `extraction_method` and `ocr_confidence` (if not null) as small metadata text.
    - A definition-list/table of every non-null field in `data` (skip `items`, shown separately), each row showing the field's Spanish label, its value, and — if present in `field_confidence` — a small confidence tag (alta/media/baja).
    - If `data.items.length > 0`, a table with columns Descripción, Cantidad, Precio Unitario, Subtotal.
    - If `warnings.length > 0`, a list of warnings (amber) showing `message` (and `field` if present).
    - If `errors.length > 0`, a list of errors (red) showing `message`.

- [ ] **Step 1: Write `UploadForm.tsx`**

```tsx
// frontend/components/UploadForm.tsx
"use client";

import { useState } from "react";
import { extractInvoice } from "@/lib/api";
import type { ExtractionResult } from "@/lib/types";

interface UploadFormProps {
  onResult: (result: ExtractionResult, fileName: string) => void;
}

export default function UploadForm({ onResult }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Seleccioná un archivo primero.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await extractInvoice(file);
      onResult(result, file.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="upload-form">
      <input
        type="file"
        accept="application/pdf,image/png,image/jpeg"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button type="submit" disabled={loading}>
        {loading ? "Procesando..." : "Extraer"}
      </button>
      {error && <p className="error-text">{error}</p>}
    </form>
  );
}
```

- [ ] **Step 2: Write `ResultView.tsx`**

```tsx
// frontend/components/ResultView.tsx
import type { ExtractionResult } from "@/lib/types";

const FIELD_LABELS: Record<string, string> = {
  tipo_comprobante: "Tipo de comprobante",
  punto_venta: "Punto de venta",
  numero_comprobante: "Número de comprobante",
  fecha_emision: "Fecha de emisión",
  cuit_emisor: "CUIT emisor",
  razon_social_emisor: "Razón social emisor",
  cuit_receptor: "CUIT receptor",
  razon_social_receptor: "Razón social receptor",
  condicion_iva_receptor: "Condición frente al IVA (receptor)",
  cae: "CAE",
  vencimiento_cae: "Vencimiento CAE",
  moneda: "Moneda",
  subtotal: "Subtotal",
  iva: "IVA",
  total: "Total",
};

const STATUS_LABELS: Record<string, string> = {
  ok: "OK",
  partial: "Parcial",
  failed: "Fallido",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "alta",
  medium: "media",
  low: "baja",
};

interface ResultViewProps {
  result: ExtractionResult;
}

export default function ResultView({ result }: ResultViewProps) {
  const fieldEntries = Object.entries(result.data).filter(
    ([key, value]) => key !== "items" && value !== null && value !== ""
  );

  return (
    <div className="result-view">
      <div className={`status-badge status-${result.status}`}>
        {STATUS_LABELS[result.status]}
      </div>
      <p className="meta-text">
        Método: {result.extraction_method ?? "N/A"}
        {result.ocr_confidence !== null && ` · Confianza OCR: ${result.ocr_confidence.toFixed(1)}%`}
      </p>

      <table className="fields-table">
        <tbody>
          {fieldEntries.map(([key, value]) => (
            <tr key={key}>
              <td>{FIELD_LABELS[key] ?? key}</td>
              <td>{String(value)}</td>
              <td>
                {result.field_confidence[key]
                  ? CONFIDENCE_LABELS[result.field_confidence[key]]
                  : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {result.data.items.length > 0 && (
        <table className="items-table">
          <thead>
            <tr>
              <th>Descripción</th>
              <th>Cantidad</th>
              <th>Precio Unitario</th>
              <th>Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {result.data.items.map((item, idx) => (
              <tr key={idx}>
                <td>{item.descripcion}</td>
                <td>{item.cantidad}</td>
                <td>{item.precio_unitario}</td>
                <td>{item.subtotal_linea}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {result.warnings.length > 0 && (
        <ul className="warnings-list">
          {result.warnings.map((w, idx) => (
            <li key={idx}>
              {w.message}
              {w.field && ` (campo: ${w.field})`}
            </li>
          ))}
        </ul>
      )}

      {result.errors.length > 0 && (
        <ul className="errors-list">
          {result.errors.map((e, idx) => (
            <li key={idx}>{e.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

From `frontend/`: `npx tsc --noEmit`
Expected: no errors (both components are unused by any page yet, but must type-check standalone).

- [ ] **Step 4: Commit**

```bash
git add frontend/components/UploadForm.tsx frontend/components/ResultView.tsx
git commit -m "feat(frontend): add UploadForm and ResultView components"
```

---

## Task 11: `HistoryList` component + `page.tsx` wiring + styles

**Files:**
- Create: `frontend/components/HistoryList.tsx`
- Modify: `frontend/app/page.tsx` (replace `create-next-app` default content)
- Modify: `frontend/app/globals.css` (replace default content with minimal styling)

**Interfaces:**
- Consumes: `UploadForm`, `ResultView`, `frontend/lib/types.ts` (`ExtractionResult`).
- Produces: the complete single-page UI. No further tasks consume this one's exports (leaf of the frontend dependency graph).

`HistoryList` props: `{ entries: { fileName: string; result: ExtractionResult }[]; selectedIndex: number | null; onSelect: (index: number) => void }`. Renders a list of buttons, one per entry, showing the file name and a small status dot (green/amber/red per `result.status`); clicking calls `onSelect(index)`; the currently `selectedIndex` entry is visually highlighted.

`page.tsx` behavior: holds `history: { fileName: string; result: ExtractionResult }[]` and `selectedIndex: number | null` in `useState`. Renders `UploadForm` with `onResult` that prepends a new entry to `history` and sets `selectedIndex` to `0`. Renders `HistoryList` (only if `history.length > 0`) and `ResultView` for `history[selectedIndex]` (only if `selectedIndex !== null`).

- [ ] **Step 1: Write `HistoryList.tsx`**

```tsx
// frontend/components/HistoryList.tsx
import type { ExtractionResult } from "@/lib/types";

interface HistoryEntry {
  fileName: string;
  result: ExtractionResult;
}

interface HistoryListProps {
  entries: HistoryEntry[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}

export default function HistoryList({ entries, selectedIndex, onSelect }: HistoryListProps) {
  return (
    <ul className="history-list">
      {entries.map((entry, idx) => (
        <li key={idx}>
          <button
            type="button"
            className={idx === selectedIndex ? "history-item selected" : "history-item"}
            onClick={() => onSelect(idx)}
          >
            <span className={`status-dot status-${entry.result.status}`} />
            {entry.fileName}
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 2: Write `app/page.tsx`**

```tsx
// frontend/app/page.tsx
"use client";

import { useState } from "react";
import UploadForm from "@/components/UploadForm";
import ResultView from "@/components/ResultView";
import HistoryList from "@/components/HistoryList";
import type { ExtractionResult } from "@/lib/types";

interface HistoryEntry {
  fileName: string;
  result: ExtractionResult;
}

export default function Home() {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  function handleResult(result: ExtractionResult, fileName: string) {
    setHistory((prev) => [{ fileName, result }, ...prev]);
    setSelectedIndex(0);
  }

  function handleSelect(index: number) {
    setSelectedIndex(index);
  }

  return (
    <main className="page">
      <h1>Extractor de Facturas ARCA</h1>
      <UploadForm onResult={handleResult} />

      <div className="layout">
        {history.length > 0 && (
          <HistoryList entries={history} selectedIndex={selectedIndex} onSelect={handleSelect} />
        )}
        {selectedIndex !== null && history[selectedIndex] && (
          <ResultView result={history[selectedIndex].result} />
        )}
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Write minimal `app/globals.css`**

```css
/* frontend/app/globals.css */
* {
  box-sizing: border-box;
}

body {
  font-family: system-ui, sans-serif;
  margin: 0;
  padding: 0;
  background: #f7f7f8;
  color: #1a1a1a;
}

.page {
  max-width: 960px;
  margin: 0 auto;
  padding: 2rem 1rem;
}

.upload-form {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 1.5rem;
}

.error-text {
  color: #b91c1c;
}

.layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 1.5rem;
}

.history-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  text-align: left;
  padding: 0.5rem;
  border: 1px solid #ddd;
  background: white;
  border-radius: 6px;
  cursor: pointer;
}

.history-item.selected {
  border-color: #2563eb;
  background: #eff6ff;
}

.status-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.status-dot.status-ok,
.status-badge.status-ok {
  background: #16a34a;
}

.status-dot.status-partial,
.status-badge.status-partial {
  background: #d97706;
}

.status-dot.status-failed,
.status-badge.status-failed {
  background: #dc2626;
}

.status-badge {
  display: inline-block;
  color: white;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  font-weight: 600;
  font-size: 0.875rem;
}

.meta-text {
  color: #555;
  font-size: 0.875rem;
}

.fields-table,
.items-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1rem;
}

.fields-table td,
.items-table td,
.items-table th {
  border-bottom: 1px solid #eee;
  padding: 0.4rem;
  text-align: left;
}

.warnings-list li {
  color: #92400e;
}

.errors-list li {
  color: #991b1b;
}
```

- [ ] **Step 4: Run the dev server and manually verify the flow**

From `frontend/` (backend must also be running from Task 7 Step 6 — start it in a separate terminal: `uvicorn app.main:app --reload --port 8000` from `backend/`):

```bash
npm run dev
```

Open `http://localhost:3000`. Upload `backend/tests/fixtures/synthetic_clean.pdf` — verify the status badge shows "OK" (green), fields render, no console errors. Upload `backend/tests/fixtures/synthetic_mismatch.pdf` — verify status "Parcial" (amber) and the `TOTAL_MISMATCH` warning message appears. Upload `backend/tests/fixtures/synthetic_unreadable.png` — verify status "Fallido" (red) and the error message appears. Click between history entries — verify the displayed result switches correctly. Stop both servers (Ctrl+C) when done.

- [ ] **Step 5: Run TypeScript check and build**

From `frontend/`: `npx tsc --noEmit && npm run build`
Expected: both succeed with no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/HistoryList.tsx frontend/app/page.tsx frontend/app/globals.css
git commit -m "feat(frontend): wire upload, result view, and session history into single page"
```

---

## Task 12: Root README

**Files:**
- Create: `README.md` (repo root)

**Interfaces:**
- Consumes: content from the design spec (`docs/superpowers/specs/2026-09-09-invoice-extractor-design.md`) and this plan — summarizes decisions, doesn't duplicate the full spec verbatim.
- Produces: the top-level document an evaluator reads first.

- [ ] **Step 1: Write the root `README.md`**

```markdown
# Extractor de Facturas ARCA

Pipeline que extrae datos estructurados (JSON) desde facturas argentinas
(formato ARCA/ex-AFIP, tipos A/B/C) a partir de un PDF o una imagen, con
validación de los datos extraídos y manejo explícito de casos de extracción
fallida o ambigua.

Prueba técnica — ver decisiones de diseño completas en
[`docs/superpowers/specs/2026-09-09-invoice-extractor-design.md`](docs/superpowers/specs/2026-09-09-invoice-extractor-design.md).

## Setup y ejecución

### Backend

Ver [`backend/README.md`](backend/README.md) para instrucciones completas
(requiere Python 3.11+ y el binario de Tesseract OCR instalado en el sistema).

```bash
cd backend
python -m venv .venv && .venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Abrir `http://localhost:3000` (con el backend corriendo en `http://localhost:8000`).

## Decisiones de diseño

- **Un solo tipo de documento (facturas ARCA/AFIP A/B/C)**, en vez de un
  extractor genérico multi-documento, para poder implementar reglas de
  extracción y validación específicas y bien probadas en el tiempo disponible,
  en vez de un extractor superficial para muchos formatos.
- **Extracción basada en reglas/regex, no en un LLM.** Es determinística,
  explicable campo por campo, no depende de una API key ni tiene costo por
  llamada, y encaja con el criterio de "manejo explícito de ambigüedad": cada
  campo no encontrado queda en `null` con un warning, nunca "alucinado".
  Se evaluó **GLM-OCR** (modelo abierto de Zhipu/Z.ai con extracción JSON
  nativa) como alternativa; se descartó para el MVP por ser muy reciente,
  requerir API key/costo, y por empujar el pipeline hacia un enfoque menos
  explicable — queda documentado como mejora futura.
- **Tesseract vía `pytesseract`** para OCR: estándar de la industria, gratuito,
  100% local, sin dependencia de servicios externos.
- **PyMuPDF como única librería de manejo de PDF**: extrae texto embebido
  directamente cuando existe, y rasteriza páginas a imagen para pasarlas a
  Tesseract cuando el PDF es un escaneo — evita depender de Poppler/`pdf2image`.
- **Pipeline síncrono (`POST /extract` responde con el resultado final)**: el
  volumen esperado (una factura por vez) y el tiempo de OCR (segundos) no
  justifican una cola de jobs asíncrona para este alcance.
- **Respuesta HTTP siempre 200 cuando el pipeline corrió**, con el estado del
  negocio (`status: "ok" | "partial" | "failed"`) en el cuerpo — separa errores
  de infraestructura/request (4xx) de resultados de negocio esperables.
- **`status` de tres niveles + warnings/errors explícitos por campo**, en vez
  de un simple ok/error, para poder mostrar exactamente qué campo falló o es
  ambiguo, con su nivel de confianza, sin fallar en silencio.
- **Frontend minimalista de una sola pantalla**, con historial solo en memoria
  de React (sin persistencia), acorde al alcance pedido para el front.

## Limitaciones actuales

- Extracción basada en regex/heurísticas: sensible a variaciones de layout no
  contempladas (facturas con diseños muy distintos a los patrones cubiertos
  pueden dar campos en `null` o de confianza baja).
- El parseo de la tabla de items es la parte más frágil del pipeline (layouts
  tabulares muy variables); cuando falla, se degrada de forma explícita
  (`items: []` + warning `ITEMS_NOT_PARSED`) en vez de fallar todo el documento.
- Sin soporte para otros tipos de documento (formularios, recibos no-ARCA,
  facturas de otros países).
- Sin persistencia de resultados (ni backend ni frontend) — cada extracción es
  independiente y el historial del frontend se pierde al recargar la página.
- Sin autenticación ni control de acceso.
- Procesamiento síncrono: un documento muy grande o de OCR lento bloquea la
  respuesta HTTP hasta terminar (aceptable para el alcance de la prueba, no
  para producción con volumen alto).

## Qué mejoraría con más tiempo

- Sumar más facturas reales anonimizadas de distintos emisores para ampliar
  la cobertura de los patrones regex y medir precisión real (no solo con
  fixtures sintéticas).
- Evaluar un enfoque híbrido: reglas primero, y un fallback a un modelo como
  GLM-OCR (o un LLM con prompt de extracción estructurada) solo cuando las
  reglas no logran completar los campos obligatorios — mejor cobertura sin
  perder la explicabilidad del camino determinístico.
- Mejorar el parseo de la tabla de items con un enfoque basado en posición
  (coordenadas de texto de PyMuPDF/Tesseract) en vez de solo regex sobre texto
  plano, para manejar mejor layouts tabulares complejos.
- Tests contra un set más grande y diverso de facturas reales, con métricas de
  precisión/recall por campo.
- Agregar historial persistente (ej. SQLite) si el caso de uso lo justifica.

## Cómo lo llevaría a producción

- Procesamiento asíncrono (cola de jobs, ej. Celery/RQ o un servicio de
  colas gestionado) en vez de bloquear la respuesta HTTP, para soportar
  volumen y archivos más pesados sin degradar la experiencia.
- Observabilidad: logging estructurado por etapa del pipeline, métricas de
  tasa de `status: failed`/`partial` por campo, alertas si la tasa de fallo
  sube (señal de que el formato de entrada cambió).
- Persistencia de resultados (base de datos) con trazabilidad de qué versión
  de las reglas de extracción generó cada resultado, para poder auditar y
  reprocesar si se mejoran las reglas.
- Autenticación/autorización si se expone a más de un usuario o cliente.
- Manejo de secretos/configuración vía variables de entorno gestionadas
  (no hardcodeadas), y despliegue containerizado (Docker) para reproducibilidad
  del entorno (especialmente la dependencia del binario de Tesseract).
- Monitoreo de deriva de precisión: si se migra a un modelo como GLM-OCR o un
  LLM, versionar prompts/modelos y tener un set de regresión para detectar
  degradación de calidad entre versiones.

## Testing

```bash
cd backend
pytest -v
```

Ver [`backend/tests/fixtures/README.md`](backend/tests/fixtures/README.md) para
el detalle de los documentos de prueba (sintéticos y reales anonimizados).
```

- [ ] **Step 2: Verify all internal links resolve**

Confirm these files exist: `docs/superpowers/specs/2026-09-09-invoice-extractor-design.md`, `backend/README.md`, `backend/tests/fixtures/README.md`. All three should already exist from earlier tasks.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add root README with setup, design decisions, limitations, and roadmap"
```

---

## Self-Review Notes (for the plan author — already applied above)

- **Spec coverage:** Section 2 (stack) → Tasks 1,3,4,9. Section 3 (folder structure) → matches File Structure section exactly. Section 4.1 (ingest) → Task 3. Section 4.2 (field extraction) → Task 4. Section 4.3 (validation) → Task 5. Section 4.4 (status) → Task 5 Step 3. Section 5 (JSON schema) → Task 1 models + Task 7 endpoint. Section 6 (API) → Task 7. Section 7 (frontend) → Tasks 9-11. Section 8 (test data) → Task 6 (synthetic) + fixtures README notes real invoices are added later by the user. Section 9 (testing) → Tasks 1,3,4,5,7. Section 10 (out of scope) → captured in Task 12 README limitations/roadmap.
- **Type consistency:** `IngestResult`, `FieldExtractionResult`, `InvoiceData`, `ExtractionResult`, `Warning`, `ErrorDetail` field names are identical across Tasks 1, 3, 4, 5, 7, and mirrored 1:1 in Task 9's TypeScript types.
- **Real fixtures:** the user has not yet provided anonymized real invoices (per the spec, Section 8). Task 6's fixtures README documents how to add them later; this plan does not block on their arrival — it ships fully working with synthetic fixtures and can absorb real ones as a follow-up without changing any code.
