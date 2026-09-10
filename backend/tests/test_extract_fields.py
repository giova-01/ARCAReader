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
