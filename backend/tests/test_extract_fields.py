# backend/tests/test_extract_fields.py
from app.pipeline.extract_fields import _parse_amount, extract_fields

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

POSITION_SORTED_ARCA_TEXT = """
ORIGINAL
PROVEEDOR EJEMPLO S.R.L.   C   FACTURA
COD. 011
Punto de Venta: 00001   Comp. Nro: 00000022

Razón Social: PROVEEDOR EJEMPLO S.R.L.                    Fecha de Emisión: 11/09/2026
Domicilio Comercial: Calle Falsa 123                      CUIT: 20123456789
Condición frente al IVA: Responsable Monotributo

CUIT: 27987654321        Apellido y Nombre / Razón Social: CLIENTE EJEMPLO S.A.
Condición frente al IVA: IVA Responsable Inscripto

Código   Producto / Servicio   Cantidad   U. Medida   Precio Unit.   % Bonif   Imp. Bonif.   Subtotal
Servicio de desarrollo de software   1,00   unidades   714219,00   0,00   0,00   714219,00

Subtotal: $ 714219,00
Importe Otros Tributos: $ 0,00
Importe Total: $ 714219,00

CAE N°: 86372596854584
Fecha de Vto. de CAE: 21/09/2026
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


def test_extracts_header_from_position_sorted_arca_text():
    result = extract_fields(POSITION_SORTED_ARCA_TEXT)

    assert result.data.tipo_comprobante == "C"
    assert result.data.punto_venta == "00001"
    assert result.data.numero_comprobante == "00000022"
    assert result.data.cuit_emisor == "20-12345678-9"
    assert result.data.razon_social_emisor == "PROVEEDOR EJEMPLO S.R.L."
    assert result.data.cuit_receptor == "27-98765432-1"
    assert result.data.razon_social_receptor == "CLIENTE EJEMPLO S.A."


def test_ignores_unlabeled_phone_number_before_issuer_cuit():
    text = """
    FACTURA C
    Teléfono: 11345678901
    Razón Social: PROVEEDOR EJEMPLO S.R.L.
    CUIT: 20123456789
    CUIT: 27987654321    Apellido y Nombre / Razón Social: CLIENTE EJEMPLO S.A.
    """

    result = extract_fields(text)

    assert result.data.cuit_emisor == "20-12345678-9"
    assert result.data.cuit_receptor == "27-98765432-1"


def test_parses_items_from_position_sorted_arca_text():
    result = extract_fields(POSITION_SORTED_ARCA_TEXT)

    assert result.items_parsed is True
    assert len(result.data.items) == 1
    assert result.data.items[0].descripcion == "Servicio de desarrollo de software"
    assert result.data.items[0].cantidad == 1.0
    assert result.data.items[0].precio_unitario == 714219.0
    assert result.data.items[0].subtotal_linea == 714219.0


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


def test_parse_amount_single_decimal_digit_is_not_corrupted():
    # Regression test: "1234,5" is a valid Argentine decimal-comma amount
    # (one decimal digit). It must NOT be treated as a thousands separator
    # and turned into 12345.0.
    assert _parse_amount("1234,5") == 1234.5


def test_parse_amount_two_decimal_digits_still_correct():
    assert _parse_amount("1234,50") == 1234.5


def test_parse_amount_thousands_and_decimal_comma_still_correct():
    assert _parse_amount("1.234,50") == 1234.5


def test_parse_amount_malformed_returns_none():
    assert _parse_amount("not-a-number") is None
