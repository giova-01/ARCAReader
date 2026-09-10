// frontend/lib/api.ts
import type { ExtractionResult } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function extractInvoice(file: File): Promise<ExtractionResult> {
  const formData = new FormData();
  formData.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_URL}/extract`, {
      method: "POST",
      body: formData,
    });
  } catch (err) {
    throw new Error("No se pudo conectar con el servidor. ¿Está corriendo el backend?");
  }

  if (!response.ok) {
    throw new Error(`Error del servidor (${response.status}): no se pudo procesar el archivo.`);
  }

  return (await response.json()) as ExtractionResult;
}
