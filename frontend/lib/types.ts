// frontend/lib/types.ts
export type FieldConfidence = "high" | "medium" | "low";
export type ExtractionStatus = "ok" | "partial" | "failed";
export type ExtractionMethod = "pdf_text" | "ocr";

export interface LineItem {
  descripcion: string;
  cantidad: number;
  precio_unitario: number;
  subtotal_linea: number;
}

export interface InvoiceData {
  tipo_comprobante: string | null;
  punto_venta: string | null;
  numero_comprobante: string | null;
  fecha_emision: string | null;
  cuit_emisor: string | null;
  razon_social_emisor: string | null;
  cuit_receptor: string | null;
  razon_social_receptor: string | null;
  condicion_iva_receptor: string | null;
  cae: string | null;
  vencimiento_cae: string | null;
  moneda: string;
  subtotal: number | null;
  iva: number | null;
  total: number | null;
  items: LineItem[];
}

export interface Warning {
  code: string;
  field: string | null;
  message: string;
}

export interface ErrorDetail {
  code: string;
  field: string | null;
  message: string;
}

export interface ExtractionResult {
  status: ExtractionStatus;
  extraction_method: ExtractionMethod | null;
  ocr_confidence: number | null;
  data: InvoiceData;
  field_confidence: Record<string, FieldConfidence>;
  warnings: Warning[];
  errors: ErrorDetail[];
}
