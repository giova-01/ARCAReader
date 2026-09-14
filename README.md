# Ejecución

## Requisitos

- Python 3.11+
- Node.js 20+
- Tesseract OCR instalado y disponible en `PATH`

## Instalar Tesseract OCR

### Windows

Descargar e instalar Tesseract desde:
`https://github.com/UB-Mannheim/tesseract/wiki`

Agregar `C:\Program Files\Tesseract-OCR` a la variable de entorno `PATH` y reiniciar la terminal.

### macOS

```bash
brew install tesseract
```

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install tesseract-ocr
```

Verificar la instalación:

```bash
tesseract --version
```

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Frontend

En otra terminal:

```powershell
cd frontend
npm install
Copy-Item .env.local.example .env.local
npm run dev
```

Abrir `http://localhost:3000`.
