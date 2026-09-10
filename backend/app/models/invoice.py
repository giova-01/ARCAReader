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
