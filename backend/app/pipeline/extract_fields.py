# backend/app/pipeline/extract_fields.py
import re
from typing import NamedTuple, Optional

from app.config import CUIT_PATTERN, DATE_PATTERN
from app.models.invoice import FieldConfidence, InvoiceData, LineItem


class FieldExtractionResult(NamedTuple):
    data: InvoiceData
    field_confidence: dict[str, FieldConfidence]
    items_parsed: bool


def _parse_amount(raw: str) -> Optional[float]:
    raw = raw.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})*,\d{2}", raw) or re.fullmatch(r"\d+,\d{2}", raw):
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
    match = re.search(r"COD.*?\b([ABC])\b", text, re.IGNORECASE)
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


def _find_cuit_receptor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    cuit_emisor, _ = _find_cuit_emisor(text)
    for match in re.finditer(CUIT_PATTERN, text):
        if match.group(0) != cuit_emisor:
            return match.group(0), "high"
    return None, None


def _find_razon_social_emisor(text: str) -> tuple[Optional[str], Optional[FieldConfidence]]:
    half = text[: len(text) // 2]
    match = re.search(CUIT_PATTERN, half) or re.search(CUIT_PATTERN, text)
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
    match = re.search(r"(?:Apellido\s+y\s+Nombre|Raz[oó]n\s+Social)\s*(?:/\s*Raz[oó]n\s+Social)?\s*:?\s*([^\n]+)", text, re.IGNORECASE)
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
    cuit_receptor = record("cuit_receptor", _find_cuit_receptor(text))
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
