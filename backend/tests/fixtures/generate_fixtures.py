"""Regenerate synthetic invoice fixtures used by test_integration.py.

Run manually with: python tests/fixtures/generate_fixtures.py
"""
import os

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FIXTURES_DIR = os.path.dirname(__file__)

CLEAN_INVOICE_TEXT = """Ejemplo SRL
CUIT: 20-12345678-6
FACTURA A
COD. 001
Pto. Vta.: 0003  Comp. Nro: 00012345
Fecha de Emision: 15/03/2026

Apellido y Nombre / Razon Social: Cliente Ejemplo
CUIT: 27-98765432-0
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
CUIT: 20-12345678-6
FACTURA A
COD. 001
Pto. Vta.: 0003  Comp. Nro: 00099999
Fecha de Emision: 20/03/2026

Apellido y Nombre / Razon Social: Cliente Discrepante
CUIT: 27-98765432-0
Responsable Inscripto

Cantidad Descripcion Precio Unit. Subtotal
1 Producto con precio incorrecto 500,00 500,00

Subtotal: $ 10000,00
IVA: $ 2100,00
Total: $ 99999,00

CAE N: 98765432109876
Fecha de Vto. de CAE: 30/03/2026
"""

# Lines rendered slightly darker/larger than the rest so that the critical
# fields (comprobante number, total) remain OCR-recognizable while the
# overall average OCR confidence still falls below LOW_OCR_CONFIDENCE_THRESHOLD.
_LOW_CONFIDENCE_EMPHASIZED_LINES = {
    "Pto. Vta.: 0003  Comp. Nro: 00012345",
    "Total: $ 12100,00",
}


def _write_text_pdf(path: str, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((36, 36), text, fontsize=9)
    doc.save(path)
    doc.close()


def _write_low_confidence_image(path: str, text: str) -> None:
    """Render a blurry, low-contrast rendition of a full invoice.

    Most lines are drawn very light and at normal size so OCR confidence
    stays low overall (below LOW_OCR_CONFIDENCE_THRESHOLD), but the
    comprobante number and total lines are drawn slightly darker/larger so
    they still come through legibly -- otherwise CRITICAL_FIELDS_MISSING
    would make the result "failed" instead of "partial", and the fixture
    would never exercise the LOW_OCR_CONFIDENCE warning it's meant to test.
    """
    img = Image.new("RGB", (1000, 800), color="white")
    draw = ImageDraw.Draw(img)
    y = 20
    for line in text.splitlines():
        if line in _LOW_CONFIDENCE_EMPHASIZED_LINES:
            font = ImageFont.load_default(size=20)
            draw.text((20, y), line, fill=(120, 120, 120), font=font)
            y += 30
        else:
            draw.text((20, y), line, fill=(195, 195, 195))
            y += 28
    img = img.filter(ImageFilter.GaussianBlur(radius=1.3))
    img.save(path)


def _write_blank_image(path: str) -> None:
    img = Image.new("RGB", (200, 200), color="white")
    img.save(path)


def main() -> None:
    _write_text_pdf(os.path.join(FIXTURES_DIR, "synthetic_clean.pdf"), CLEAN_INVOICE_TEXT)
    _write_text_pdf(os.path.join(FIXTURES_DIR, "synthetic_mismatch.pdf"), MISMATCH_INVOICE_TEXT)
    _write_low_confidence_image(
        os.path.join(FIXTURES_DIR, "synthetic_low_confidence.png"), CLEAN_INVOICE_TEXT
    )
    _write_blank_image(os.path.join(FIXTURES_DIR, "synthetic_unreadable.png"))
    print("Fixtures generated in", FIXTURES_DIR)


if __name__ == "__main__":
    main()
