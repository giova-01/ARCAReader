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
        cuit_emisor="20-12345678-6",
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
    field_result = _field_result(cae="not-a-valid-cae")
    result = build_extraction_result(ingest_result, field_result)
    assert result.status == "partial"
    codes = [w.code for w in result.warnings]
    assert "MISSING_REQUIRED_FIELD" not in codes  # cae is not required


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
