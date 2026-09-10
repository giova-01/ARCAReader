// frontend/components/UploadForm.tsx
"use client";

import { useState } from "react";
import { extractInvoice } from "@/lib/api";
import type { ExtractionResult } from "@/lib/types";

interface UploadFormProps {
  onResult: (result: ExtractionResult, fileName: string) => void;
}

export default function UploadForm({ onResult }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      <input
        type="file"
        accept="application/pdf,image/png,image/jpeg"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button type="submit" disabled={loading}>
        {loading ? "Procesando..." : "Extraer"}
      </button>
      {error && <p className="error-text">{error}</p>}
    </form>
  );
}
