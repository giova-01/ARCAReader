# Fixtures de prueba

## Sintéticas (generadas)

Generadas por `generate_fixtures.py`. Para regenerarlas:

```bash
python tests/fixtures/generate_fixtures.py
```

- `synthetic_clean.pdf` — PDF con texto embebido, factura completa y consistente (camino feliz, `status: ok`).
- `synthetic_mismatch.pdf` — PDF con texto embebido, pero con inconsistencia matemática deliberada entre subtotal/IVA/total (`status: partial`, warning `TOTAL_MISMATCH`).
- `synthetic_low_confidence.png` — imagen con texto borroso de baja calidad, para forzar confianza OCR baja (`status: partial`, warning `LOW_OCR_CONFIDENCE`).
- `synthetic_unreadable.png` — imagen en blanco sin texto, documento no procesable (`status: failed`).

## Reales anonimizadas

Cuando el usuario provea facturas ARCA/AFIP reales anonimizadas, agregarlas a esta
carpeta con un nombre descriptivo (ej. `real_factura_a_01.pdf`). Antes de commitear,
verificar que no contengan CUIT, razón social, ni datos personales reales sin
anonimizar — reemplazar por valores ficticios si es necesario.
