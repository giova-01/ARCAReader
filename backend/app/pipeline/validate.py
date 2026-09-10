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
