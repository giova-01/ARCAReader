// frontend/components/UploadForm.tsx
"use client";

import { useRef, useState } from "react";
import { extractInvoice } from "@/lib/api";
import type { ExtractionResult } from "@/lib/types";
import { clearFileInput } from "./file-input";

const ACCEPTED_FILE_TYPES = ["application/pdf", "image/png", "image/jpeg"];

function UploadIcon() {
  return (
    <svg
      aria-hidden="true"
      width="40"
      height="40"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <path
        d="M12 16V4M12 4L7 9M12 4l5 5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DocumentIcon() {
  return (
    <svg
      aria-hidden="true"
      width="36"
      height="36"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <path
        d="M7 3h7l4 4v14H7a2 2 0 01-2-2V5a2 2 0 012-2z"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M14 3v5h5M9 13h6M9 17h6" strokeLinecap="round" />
    </svg>
  );
}

interface UploadFormProps {
  onResult: (result: ExtractionResult, fileName: string) => void;
}

export default function UploadForm({ onResult }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDragOver(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    const droppedFile = event.dataTransfer.files?.[0];

    if (!droppedFile) {
      return;
    }

    if (!ACCEPTED_FILE_TYPES.includes(droppedFile.type)) {
      setError("Formato no soportado. Subí un PDF, PNG o JPG.");
      return;
    }

    setFile(droppedFile);
    setError(null);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Seleccioná un archivo primero.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await extractInvoice(file);
      onResult(result, file.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="upload-form">
      <div
        className={`upload-dropzone${isDragging ? " dragging" : ""}${file ? " has-file" : ""}${loading ? " disabled" : ""}`}
        onClick={() => !loading && inputRef.current?.click()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,image/png,image/jpeg"
          className="visually-hidden"
          aria-label="Seleccionar factura"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          disabled={loading}
        />

        {file ? (
          <div className="dropzone-file-info">
            <DocumentIcon />
            <span className="dropzone-file-name">{file.name}</span>
            <button
              type="button"
              className="btn-remove-file"
              onClick={(event) => {
                event.stopPropagation();
                setFile(null);
                clearFileInput(inputRef.current);
              }}
              disabled={loading}
            >
              Quitar
            </button>
          </div>
        ) : (
          <div className="dropzone-empty-state">
            <UploadIcon />
            <p>
              {isDragging
                ? "Soltá el archivo acá"
                : "Arrastrá tu factura acá o hacé click para seleccionar"}
            </p>
            <p className="dropzone-hint">PDF, PNG o JPG</p>
          </div>
        )}
      </div>

      <button type="submit" className="btn-primary" disabled={loading || !file}>
        {loading ? "Procesando..." : "Extraer datos"}
      </button>
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
