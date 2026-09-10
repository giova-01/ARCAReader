"""Regenerate synthetic invoice fixtures used by test_integration.py.

Run manually with: python tests/fixtures/generate_fixtures.py
"""
import io
import os

import fitz
from PIL import Image, ImageDraw, ImageFilter

FIXTURES_DIR = os.path.dirname(__file__)

CLEAN_INVOICE_TEXT = """Ejemplo SRL
CUIT: 20-12345678-6
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
CUIT: 20-12345678-6
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
