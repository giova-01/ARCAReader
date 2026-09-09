# Extractor de datos estructurados de facturas (ARCA/AFIP) — Diseño

**Fecha:** 2026-09-09
**Contexto:** Prueba técnica (etapa 2 de proceso de selección). Consigna: construir un
pipeline que extraiga datos estructurados (JSON) desde documentos con formato variable,
con validación y manejo explícito de casos de extracción fallida o ambigua.

**Alcance elegido:** Extractor de facturas argentinas (formato ARCA, ex-AFIP), tipos A/B/C,
con cabecera + líneas de detalle (items).

## 1. Objetivo y criterios de éxito

- Pipeline funcional end-to-end: subir un documento (PDF o imagen) → texto (parsing
  directo o OCR) → datos estructurados → validación → JSON de salida.
- Los casos de baja confianza, campos faltantes o documento ilegible deben quedar
  explícitos en el JSON de salida (nunca fallar en silencio ni devolver datos
  incorrectos como si fueran confiables).
- Código legible, bien organizado, con buen criterio de ingeniería — no
  necesariamente "production-grade" completo, pero sí demostrar decisiones justificadas.
- README que explique decisiones de diseño, limitaciones, mejoras futuras y camino a
  producción.

## 2. Stack y librerías

- **Backend:** Python 3.11+, FastAPI (endpoint síncrono), Uvicorn.
- **PDF (texto y rasterizado):** PyMuPDF (`pymupdf`, import `fitz`) — única
  dependencia para PDFs: extrae texto embebido cuando existe, y rasteriza páginas a
  imagen (para pasarlas a OCR) cuando el PDF es un escaneo sin capa de texto.
- **OCR (imágenes y PDFs escaneados):** Tesseract vía `pytesseract`. Requiere el
  binario de Tesseract instalado en el sistema (documentar instalación en Windows/Mac/Linux
  en el README) además del paquete pip.
- **Estructuración de campos:** reglas + regex/heurísticas (sin LLM). Determinístico,
  explicable, sin dependencias externas ni API keys.
- **Validación de datos:** Pydantic (schemas + validators) para formato/obligatoriedad,
  más funciones de validación de consistencia numérica ad-hoc.
- **Frontend:** Next.js (App Router), minimalista, sin librería de UI pesada
  (Tailwind opcional para estilos rápidos). Sin persistencia server-side.
- **Alternativa evaluada y descartada para el MVP:** GLM-OCR (modelo abierto de
  Zhipu/Z.ai, MIT, #1 en benchmark OmniDocBench, con SDK `pip install glmocr` y
  extracción JSON nativa vía su API cloud). Se descarta para el MVP por ser muy
  reciente (semanas), requerir API key y costo por uso, y por empujar el pipeline
  hacia un enfoque basado en LLM en vez de reglas explicables. Se documenta en el
  README como alternativa moderna a considerar a futuro.

## 3. Estructura de carpetas

```
/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app, endpoint POST /extract
│   │   ├── pipeline/
│   │   │   ├── ingest.py          # detecta tipo de archivo, extrae texto (PyMuPDF) u OCR (pytesseract)
│   │   │   ├── extract_fields.py  # regex/heurísticas: cabecera + items desde texto plano
│   │   │   └── validate.py        # validación Pydantic + consistencia numérica
│   │   ├── models/
│   │   │   └── invoice.py         # schemas Pydantic (InvoiceData, LineItem, ExtractionResult, etc.)
│   │   └── config.py               # constantes (tolerancias, regex patterns, umbrales de confianza)
│   ├── tests/
│   │   ├── fixtures/               # facturas de prueba (reales anonimizadas + sintéticas)
│   │   └── test_*.py
│   ├── requirements.txt
│   └── README.md                   # setup/run específico del backend
├── frontend/
│   ├── app/
│   │   └── page.tsx                 # única pantalla: upload + resultado + historial
│   ├── components/
│   │   ├── UploadForm.tsx
│   │   ├── ResultView.tsx
│   │   └── HistoryList.tsx
│   ├── package.json
│   └── README.md                    # setup/run específico del frontend
├── docs/
│   └── superpowers/specs/           # este documento
└── README.md                        # overview, decisiones de diseño, limitaciones, roadmap
```

## 4. Pipeline interno (backend)

### 4.1 Etapa de ingesta (`ingest.py`)

1. Detectar tipo de archivo por extensión/mimetype (`.pdf`, `.png`, `.jpg`, `.jpeg`).
2. Si es PDF:
   - Abrir con PyMuPDF, extraer texto de cada página con `page.get_text()`.
   - Si el texto extraído es significativo (longitud > umbral mínimo, ej. 20
     caracteres alfanuméricos), se considera "PDF con texto" → usar ese texto
     directamente (sin OCR). Método de extracción registrado como `"pdf_text"`.
   - Si el texto es vacío/insuficiente, se considera "PDF escaneado" → rasterizar
     cada página a imagen (`page.get_pixmap()`) y correr Tesseract sobre cada imagen,
     concatenando el texto resultante. Método registrado como `"ocr"`.
3. Si es imagen (PNG/JPG): correr Tesseract directamente. Método `"ocr"`.
4. Tesseract devuelve, además del texto, datos de confianza por palabra
   (`pytesseract.image_to_data`) — se calcula una confianza OCR promedio de la página,
   usada más adelante para marcar el resultado global como de baja confianza si es
   muy baja (umbral configurable, ej. < 40%).
5. Si no se pudo extraer ningún texto utilizable (documento ilegible, archivo
   corrupto, formato no soportado): la etapa devuelve texto vacío y un flag de error,
   que la etapa de extracción/validación transforma en `status: "failed"` con un
   error explícito — el pipeline NO continúa intentando extraer campos de texto vacío.

### 4.2 Etapa de extracción de campos (`extract_fields.py`)

A partir del texto plano (de cualquier fuente), se buscan los siguientes campos
usando regex y keywords típicas de facturas ARCA/AFIP. Cada campo extraído registra
también un nivel de confianza (`high` / `medium` / `low`) según qué tan inequívoco
fue el match (ej: "Total: $" seguido de un número = alta confianza; un número
suelto cerca de la palabra "total" sin separador claro = confianza media).

**Cabecera:**
| Campo | Regex/heurística aproximada | Obligatorio |
|---|---|---|
| `tipo_comprobante` | Letra grande A/B/C cerca de "COD." o en el recuadro superior; también inferible por prefijo "FACTURA A/B/C" | Sí |
| `punto_venta` | Patrón `\d{4,5}` cerca de "Pto. Vta." / "P.V." | Sí |
| `numero_comprobante` | Patrón `\d{8}` cerca de "Comp. Nro" / "N°" | Sí |
| `fecha_emision` | Patrón de fecha `\d{2}/\d{2}/\d{4}` cerca de "Fecha de Emisión" | Sí |
| `cuit_emisor` | Patrón CUIT `\d{2}-\d{8}-\d{1}` cerca de "CUIT" en la mitad superior del documento | Sí |
| `cuit_receptor` | Igual patrón CUIT, cerca de "CUIT" en sección "Cliente/Receptor" | No |
| `razon_social_emisor` | Texto en la cabecera, antes del CUIT emisor | Sí |
| `razon_social_receptor` | Texto cerca de "Apellido y Nombre / Razón Social" en sección cliente | No |
| `condicion_iva_receptor` | Keywords: "Responsable Inscripto", "Consumidor Final", "Monotributista", etc. | No |
| `cae` | Patrón `\d{14}` cerca de "CAE N°" | No (pero si falta, warning) |
| `vencimiento_cae` | Fecha cerca de "Fecha de Vto. de CAE" | No |
| `moneda` | Default "ARS" si no se detecta símbolo distinto | No |
| `subtotal` | Monto cerca de "Subtotal" | Sí |
| `iva` | Monto cerca de "IVA" | No |
| `total` | Monto cerca de "Total" (última coincidencia, para evitar confundir con subtotales parciales) | Sí |

**Líneas de detalle (items):** se intenta segmentar la zona tabular del texto
(entre encabezado de tabla tipo "Cantidad Descripción Precio Unit. Subtotal" y el
inicio de los totales) y parsear cada línea con regex a:
`{ descripcion, cantidad, precio_unitario, subtotal_linea }`.
Dado que el layout tabular es lo más variable entre facturas, este es el punto del
pipeline con mayor probabilidad de fallo parcial — si no se puede segmentar la
tabla de forma confiable, se devuelve `items: []` con un warning explícito
(`ITEMS_NOT_PARSED`), sin bloquear el resto de la extracción de cabecera.

### 4.3 Etapa de validación (`validate.py`)

1. **Formato** (vía Pydantic validators): fecha parseable, CUIT con patrón
   `\d{2}-\d{8}-\d{1}` y dígito verificador válido, CAE numérico de 14 dígitos,
   montos numéricos no negativos.
2. **Obligatoriedad:** si falta algún campo marcado como obligatorio en la tabla
   anterior, se agrega un warning `MISSING_REQUIRED_FIELD` con el nombre del campo,
   y el campo queda `null` en el JSON (nunca se inventa un valor).
3. **Consistencia numérica:**
   - `sum(item.subtotal_linea for item in items) ≈ subtotal` (tolerancia ±1%, para
     redondeos) → si no coincide y hay items, warning `ITEMS_SUBTOTAL_MISMATCH`.
   - `subtotal + iva ≈ total` (misma tolerancia) → si no coincide, warning
     `TOTAL_MISMATCH`.
   - Estas validaciones solo corren si los campos involucrados no son `null`.
4. **Confianza OCR:** si la confianza promedio del OCR fue baja (umbral configurable),
   warning `LOW_OCR_CONFIDENCE` a nivel documento.

### 4.4 Determinación de `status` global

- `"ok"`: todos los campos obligatorios presentes, sin warnings de consistencia.
- `"partial"`: hay datos utilizables pero con uno o más warnings (campo faltante no
  crítico, inconsistencia numérica, items no parseados, confianza OCR baja).
- `"failed"`: no se pudo extraer texto del documento, o faltan campos obligatorios
  críticos (ej. no se detectó ningún monto ni número de comprobante) — el documento
  se considera no procesable.

## 5. Schema de salida (JSON)

```json
{
  "status": "partial",
  "extraction_method": "ocr",
  "ocr_confidence": 62.4,
  "data": {
    "tipo_comprobante": "A",
    "punto_venta": "0003",
    "numero_comprobante": "00012345",
    "fecha_emision": "2026-03-15",
    "cuit_emisor": "20-12345678-9",
    "razon_social_emisor": "Ejemplo SRL",
    "cuit_receptor": null,
    "razon_social_receptor": "Cliente Ejemplo",
    "condicion_iva_receptor": "Responsable Inscripto",
    "cae": "12345678901234",
    "vencimiento_cae": "2026-03-25",
    "moneda": "ARS",
    "subtotal": 10000.00,
    "iva": 2100.00,
    "total": 12100.00,
    "items": [
      { "descripcion": "Servicio de consultoría", "cantidad": 1, "precio_unitario": 10000.00, "subtotal_linea": 10000.00 }
    ]
  },
  "field_confidence": {
    "tipo_comprobante": "high",
    "total": "high",
    "cuit_receptor": "low"
  },
  "warnings": [
    { "code": "MISSING_REQUIRED_FIELD", "field": "cuit_receptor", "message": "No se pudo detectar el CUIT del receptor." }
  ],
  "errors": []
}
```

- `status`: `"ok" | "partial" | "failed"`.
- `extraction_method`: `"pdf_text" | "ocr"`.
- `ocr_confidence`: `null` si el método fue `pdf_text`.
- `data`: siempre presente (puede tener campos en `null`), incluso en `status: "failed"`
  (con lo poco que se haya podido extraer, si algo).
- `warnings`: problemas no bloqueantes (campo faltante, inconsistencia, baja confianza).
- `errors`: problemas bloqueantes (ej. `UNREADABLE_DOCUMENT`, `UNSUPPORTED_FILE_TYPE`)
  — presentes solo cuando `status: "failed"`.

## 6. API (backend)

- `POST /extract` — `multipart/form-data` con el archivo. Responde con el JSON de
  arriba. Código HTTP siempre 200 si el pipeline corrió (el estado del negocio va en
  `status`, no en el código HTTP) — 4xx solo para errores de request en sí (archivo
  ausente, tipo de contenido inválido, archivo demasiado grande).
- Swagger/OpenAPI autogenerado por FastAPI en `/docs`.
- CORS habilitado para el origen del frontend en desarrollo (`localhost:3000`).

## 7. Frontend (Next.js)

- Página única (`app/page.tsx`):
  - `UploadForm`: input de archivo (PDF/imagen) + botón "Extraer". Llama a
    `POST /extract` del backend.
  - `ResultView`: muestra el JSON de forma legible — status con color (verde/ámbar/
    rojo para ok/partial/failed), tabla de campos extraídos con su confianza,
    lista de warnings/errors, y los items en una tabla.
  - `HistoryList`: lista de extracciones realizadas en la sesión actual (estado de
    React, sin persistencia) — click en una entrega vuelve a mostrar su `ResultView`.
- Sin autenticación, sin base de datos, sin SSR especial — todo client-side hacia la API.
- URL del backend configurable vía variable de entorno (`NEXT_PUBLIC_API_URL`).

## 8. Datos de prueba

- **Principal:** facturas ARCA/AFIP reales, anonimizadas por el usuario (a proveer;
  se incorporan a `backend/tests/fixtures/` cuando estén disponibles). Antes de
  commitear, verificar que no contengan CUIT/razón social/datos personales reales
  sin anonimizar.
- **Complementario:** 2-3 facturas sintéticas generadas para cubrir casos específicos
  del pipeline que las reales podrían no cubrir:
  - Un PDF con texto embebido, formato limpio (camino feliz, `status: ok`).
  - Una imagen escaneada con calidad degradada (para forzar OCR de baja confianza,
    `status: partial` con `LOW_OCR_CONFIDENCE`).
  - Una factura con inconsistencia matemática deliberada (items vs. total no
    coinciden, `status: partial` con `TOTAL_MISMATCH`).
  - Un archivo no procesable (imagen en blanco o PDF vacío) para probar
    `status: failed`.

## 9. Testing

- Backend: tests unitarios por etapa (`ingest`, `extract_fields`, `validate`) con
  texto de entrada fijo (sin depender de OCR real en los tests unitarios, para que
  sean rápidos y determinísticos), más 1-2 tests de integración end-to-end contra
  los fixtures reales/sintéticos verificando el `status` esperado.
- Frontend: no se requieren tests automatizados dado el alcance minimalista (verificar
  manualmente el flujo subir → ver resultado).

## 10. Fuera de alcance (documentar en README como limitaciones/roadmap)

- Soporte para otros tipos de documento (formularios, recibos no-ARCA).
- Extracción vía LLM (evaluado GLM-OCR, descartado por las razones ya explicadas).
- Persistencia server-side / base de datos / autenticación.
- Procesamiento asíncrono / colas (aceptable de forma síncrona dado el volumen y
  tiempo de OCR esperado para una factura).
- Reentrenamiento o fine-tuning de modelos OCR.
- Internacionalización de formatos de factura fuera de Argentina.
