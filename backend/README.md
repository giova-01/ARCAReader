# Backend — Extractor de Facturas ARCA

API FastAPI que recibe una factura (PDF o imagen) y devuelve datos estructurados
en JSON, con validación y manejo explícito de casos ambiguos o fallidos.

## Requisitos

- Python 3.11+
- Tesseract OCR instalado en el sistema (binario, no solo el paquete pip):
  - **Windows:** descargar el instalador desde
    https://github.com/UB-Mannheim/tesseract/wiki e instalar. Agregar la carpeta
    de instalación (ej. `C:\Program Files\Tesseract-OCR`) al PATH, o configurar
    `pytesseract.pytesseract.tesseract_cmd` apuntando al ejecutable.
  
    **Nota:** el instalador de Tesseract en Windows no siempre agrega el binario al PATH automáticamente. Si al correr el backend aparece un error `TesseractNotFoundError`, verificá que `C:\Program Files\Tesseract-OCR` esté en la variable de entorno PATH (Sistema > Variables de entorno), o agregalo manualmente y reiniciá la terminal.
  
  - **macOS:** `brew install tesseract`
  - **Linux (Debian/Ubuntu):** `sudo apt install tesseract-ocr`

## Setup

```bash
cd backend
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Correr el servidor

```bash
uvicorn app.main:app --reload --port 8000
```

La API queda disponible en `http://localhost:8000`, con documentación interactiva
(Swagger) en `http://localhost:8000/docs`.

## Probar el endpoint manualmente

```bash
curl -F "file=@tests/fixtures/synthetic_clean.pdf" http://localhost:8000/extract
```

## Tests

```bash
pytest -v
```

## Regenerar fixtures sintéticas

```bash
python tests/fixtures/generate_fixtures.py
```

## Estructura

- `app/pipeline/ingest.py` — detecta tipo de archivo, extrae texto de PDF o corre OCR.
- `app/pipeline/extract_fields.py` — reglas/regex para estructurar campos de factura ARCA.
- `app/pipeline/validate.py` — validación de formato, obligatoriedad y consistencia numérica.
- `app/models/invoice.py` — schemas Pydantic de request/response.
- `app/main.py` — endpoint `POST /extract`.
