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
