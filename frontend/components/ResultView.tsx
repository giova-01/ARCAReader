// frontend/components/ResultView.tsx
"use client";

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

const FIELD_GROUPS: { title: string; keys: string[] }[] = [
  {
    title: "Comprobante",
    keys: [
      "tipo_comprobante",
      "punto_venta",
      "numero_comprobante",
      "fecha_emision",
      "cae",
      "vencimiento_cae",
    ],
  },
  {
    title: "Emisor",
    keys: ["cuit_emisor", "razon_social_emisor"],
  },
  {
    title: "Receptor",
    keys: ["cuit_receptor", "razon_social_receptor", "condicion_iva_receptor"],
  },
  {
    title: "Montos",
    keys: ["moneda", "subtotal", "iva", "total"],
  },
];

interface ResultViewProps {
  result: ExtractionResult;
}

export default function ResultView({ result }: ResultViewProps) {
  const fieldEntries = Object.entries(result.data).filter(
    ([key, value]) => key !== "items" && value !== null && value !== ""
  );
  const visibleFields = new Map(fieldEntries);

  function handleDownloadJson() {
    const json = JSON.stringify(result.data, null, 2);
    const blob = new Blob([json], { type: "application/json;charset=utf-8" });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const { punto_venta: puntoVenta, numero_comprobante: numeroComprobante } = result.data;

    link.href = objectUrl;
    link.download =
      puntoVenta && numeroComprobante
        ? `factura-${puntoVenta}-${numeroComprobante}.json`
        : "factura-extraida.json";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }

  return (
    <div className="result-view">
      <div className="result-header">
        <div className="result-header-info">
          <div className={`status-badge status-${result.status}`}>
            {STATUS_LABELS[result.status]}
          </div>
          <p className="meta-text">
            Método: {result.extraction_method ?? "N/A"}
            {result.ocr_confidence !== null &&
              ` · Confianza OCR: ${result.ocr_confidence.toFixed(1)}%`}
          </p>
        </div>
        <button type="button" className="btn-secondary" onClick={handleDownloadJson}>
          Descargar JSON
        </button>
      </div>

      <div className="field-groups">
        {FIELD_GROUPS.map((group) => {
          const groupFields = group.keys
            .filter((key) => visibleFields.has(key))
            .map((key) => [key, visibleFields.get(key)] as const);

          if (groupFields.length === 0) {
            return null;
          }

          return (
            <section key={group.title} className="field-group">
              <h2 className="field-group-title">{group.title}</h2>
              <div className="field-grid">
                {groupFields.map(([key, value]) => (
                  <div key={key} className="field-item">
                    <span className="field-label">{FIELD_LABELS[key] ?? key}</span>
                    <span className="field-value">{String(value)}</span>
                    {result.field_confidence[key] && (
                      <span
                        className={`confidence-tag confidence-${result.field_confidence[key]}`}
                      >
                        {CONFIDENCE_LABELS[result.field_confidence[key]]}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {result.data.items.length > 0 && (
        <section className="items-section">
          <h2 className="result-section-title">Ítems de la factura</h2>
          <div className="items-table-wrapper">
            <table className="items-table">
              <thead>
                <tr>
                  <th>Descripción</th>
                  <th>Cantidad</th>
                  <th>Precio unitario</th>
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
          </div>
        </section>
      )}

      {result.warnings.length > 0 && (
        <div className="banner banner-warning">
          <span className="banner-icon" aria-hidden="true">
            !
          </span>
          <div>
            <strong>Advertencias</strong>
            <ul>
              {result.warnings.map((warning, idx) => (
                <li key={idx}>
                  {warning.message}
                  {warning.field && ` (campo: ${warning.field})`}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {result.errors.length > 0 && (
        <div className="banner banner-error" role="alert">
          <span className="banner-icon" aria-hidden="true">
            ×
          </span>
          <div>
            <strong>Errores</strong>
            <ul>
              {result.errors.map((error, idx) => (
                <li key={idx}>{error.message}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
