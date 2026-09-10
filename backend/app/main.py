# backend/app/main.py
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.config import MAX_UPLOAD_SIZE_BYTES
from app.models.invoice import ExtractionResult
from app.pipeline.extract_fields import extract_fields
from app.pipeline.ingest import ingest_document
from app.pipeline.validate import build_extraction_result

app = FastAPI(title="Extractor de Facturas ARCA")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/extract", response_model=ExtractionResult)
async def extract(file: UploadFile = File(...)) -> ExtractionResult:
    file_bytes = await file.read()
    if not file.filename or not file_bytes:
        raise HTTPException(status_code=400, detail="No se recibió ningún archivo.")

    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="El archivo excede el tamaño máximo permitido.")

    ingest_result = ingest_document(file_bytes, file.filename)

    field_result = extract_fields(ingest_result.text) if ingest_result.readable else None

    return build_extraction_result(ingest_result, field_result)
