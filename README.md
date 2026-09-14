# Ejecución

## Requisitos

- Python 3.11+
- Node.js 20+
- Tesseract OCR instalado y disponible en `PATH`

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
