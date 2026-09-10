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
