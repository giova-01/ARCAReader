// frontend/components/ResultView.tsx
import type { ExtractionResult } from "@/lib/types";

const FIELD_LABELS: Record<string, string> = {
  tipo_comprobante: "Tipo de comprobante",
  punto_venta: "Punto de venta",
  numero_comprobante: "Número de comprobante",
  fecha_emision: "Fecha de emisión",
  cuit_emisor: "CUIT emisor",
  razon_social_emisor: "Razón social emisor",
  cuit_receptor: "CUIT receptor",
  razon_social_receptor: "Razón social receptor",
  condicion_iva_receptor: "Condición frente al IVA (receptor)",
  cae: "CAE",
  vencimiento_cae: "Vencimiento CAE",
  moneda: "Moneda",
  subtotal: "Subtotal",
  iva: "IVA",
  total: "Total",
};

const STATUS_LABELS: Record<string, string> = {
  ok: "OK",
  partial: "Parcial",
  failed: "Fallido",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "alta",
  medium: "media",
  low: "baja",
};

interface ResultViewProps {
  result: ExtractionResult;
}

export default function ResultView({ result }: ResultViewProps) {
  const fieldEntries = Object.entries(result.data).filter(
    ([key, value]) => key !== "items" && value !== null && value !== ""
  );

  return (
    <div className="result-view">
      <div className={`status-badge status-${result.status}`}>
        {STATUS_LABELS[result.status]}
      </div>
      <p className="meta-text">
        Método: {result.extraction_method ?? "N/A"}
        {result.ocr_confidence !== null && ` · Confianza OCR: ${result.ocr_confidence.toFixed(1)}%`}
      </p>

      <table className="fields-table">
        <tbody>
          {fieldEntries.map(([key, value]) => (
            <tr key={key}>
              <td>{FIELD_LABELS[key] ?? key}</td>
              <td>{String(value)}</td>
              <td>
                {result.field_confidence[key]
                  ? CONFIDENCE_LABELS[result.field_confidence[key]]
                  : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {result.data.items.length > 0 && (
        <table className="items-table">
          <thead>
            <tr>
              <th>Descripción</th>
              <th>Cantidad</th>
              <th>Precio Unitario</th>
              <th>Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {result.data.items.map((item, idx) => (
              <tr key={idx}>
                <td>{item.descripcion}</td>
                <td>{item.cantidad}</td>
                <td>{item.precio_unitario}</td>
                <td>{item.subtotal_linea}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {result.warnings.length > 0 && (
        <ul className="warnings-list">
          {result.warnings.map((w, idx) => (
            <li key={idx}>
              {w.message}
              {w.field && ` (campo: ${w.field})`}
            </li>
          ))}
        </ul>
      )}

      {result.errors.length > 0 && (
        <ul className="errors-list">
          {result.errors.map((e, idx) => (
            <li key={idx}>{e.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
