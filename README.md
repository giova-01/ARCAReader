# Extractor de Facturas ARCA

Pipeline que extrae datos estructurados (JSON) desde facturas argentinas
(formato ARCA/ex-AFIP, tipos A/B/C) a partir de un PDF o una imagen, con
validación de los datos extraídos y manejo explícito de casos de extracción
fallida o ambigua.

Prueba técnica — ver decisiones de diseño completas en
[`docs/superpowers/specs/2026-09-09-invoice-extractor-design.md`](docs/superpowers/specs/2026-09-09-invoice-extractor-design.md).

## Setup y ejecución

### Backend

Ver [`backend/README.md`](backend/README.md) para instrucciones completas
(requiere Python 3.11+ y el binario de Tesseract OCR instalado en el sistema).

```bash
cd backend
python -m venv .venv && .venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Abrir `http://localhost:3000` (con el backend corriendo en `http://localhost:8000`).

## Decisiones de diseño

- **Un solo tipo de documento (facturas ARCA/AFIP A/B/C)**, en vez de un
  extractor genérico multi-documento, para poder implementar reglas de
  extracción y validación específicas y bien probadas en el tiempo disponible,
  en vez de un extractor superficial para muchos formatos.
- **Extracción basada en reglas/regex, no en un LLM.** Es determinística,
  explicable campo por campo, no depende de una API key ni tiene costo por
  llamada, y encaja con el criterio de "manejo explícito de ambigüedad": cada
  campo no encontrado queda en `null` con un warning, nunca "alucinado".
  Se evaluó **GLM-OCR** (modelo abierto de Zhipu/Z.ai con extracción JSON
  nativa) como alternativa; se descartó para el MVP por ser muy reciente,
  requerir API key/costo, y por empujar el pipeline hacia un enfoque menos
  explicable — queda documentado como mejora futura.
- **Tesseract vía `pytesseract`** para OCR: estándar de la industria, gratuito,
  100% local, sin dependencia de servicios externos.
- **PyMuPDF como única librería de manejo de PDF**: extrae texto embebido
  directamente cuando existe, y rasteriza páginas a imagen para pasarlas a
  Tesseract cuando el PDF es un escaneo — evita depender de Poppler/`pdf2image`.
- **Pipeline síncrono (`POST /extract` responde con el resultado final)**: el
  volumen esperado (una factura por vez) y el tiempo de OCR (segundos) no
  justifican una cola de jobs asíncrona para este alcance.
- **Respuesta HTTP siempre 200 cuando el pipeline corrió**, con el estado del
  negocio (`status: "ok" | "partial" | "failed"`) en el cuerpo — separa errores
  de infraestructura/request (4xx) de resultados de negocio esperables.
- **`status` de tres niveles + warnings/errors explícitos por campo**, en vez
  de un simple ok/error, para poder mostrar exactamente qué campo falló o es
  ambiguo, con su nivel de confianza, sin fallar en silencio.
- **Frontend minimalista de una sola pantalla**, con historial solo en memoria
  de React (sin persistencia), acorde al alcance pedido para el front.

## Limitaciones actuales

- Extracción basada en regex/heurísticas: sensible a variaciones de layout no
  contempladas (facturas con diseños muy distintos a los patrones cubiertos
  pueden dar campos en `null` o de confianza baja).
- El parseo de la tabla de items es la parte más frágil del pipeline (layouts
  tabulares muy variables); cuando falla, se degrada de forma explícita
  (`items: []` + warning `ITEMS_NOT_PARSED`) en vez de fallar todo el documento.
- Sin soporte para otros tipos de documento (formularios, recibos no-ARCA,
  facturas de otros países).
- Sin persistencia de resultados (ni backend ni frontend) — cada extracción es
  independiente y el historial del frontend se pierde al recargar la página.
- Sin autenticación ni control de acceso.
- Procesamiento síncrono: un documento muy grande o de OCR lento bloquea la
  respuesta HTTP hasta terminar (aceptable para el alcance de la prueba, no
  para producción con volumen alto).

## Qué mejoraría con más tiempo

- Sumar más facturas reales anonimizadas de distintos emisores para ampliar
  la cobertura de los patrones regex y medir precisión real (no solo con
  fixtures sintéticas).
- Evaluar un enfoque híbrido: reglas primero, y un fallback a un modelo como
  GLM-OCR (o un LLM con prompt de extracción estructurada) solo cuando las
  reglas no logran completar los campos obligatorios — mejor cobertura sin
  perder la explicabilidad del camino determinístico.
- Mejorar el parseo de la tabla de items con un enfoque basado en posición
  (coordenadas de texto de PyMuPDF/Tesseract) en vez de solo regex sobre texto
  plano, para manejar mejor layouts tabulares complejos.
- Tests contra un set más grande y diverso de facturas reales, con métricas de
  precisión/recall por campo.
- Agregar historial persistente (ej. SQLite) si el caso de uso lo justifica.

## Cómo lo llevaría a producción

- Procesamiento asíncrono (cola de jobs, ej. Celery/RQ o un servicio de
  colas gestionado) en vez de bloquear la respuesta HTTP, para soportar
  volumen y archivos más pesados sin degradar la experiencia.
- Observabilidad: logging estructurado por etapa del pipeline, métricas de
  tasa de `status: failed`/`partial` por campo, alertas si la tasa de fallo
  sube (señal de que el formato de entrada cambió).
- Persistencia de resultados (base de datos) con trazabilidad de qué versión
  de las reglas de extracción generó cada resultado, para poder auditar y
  reprocesar si se mejoran las reglas.
- Autenticación/autorización si se expone a más de un usuario o cliente.
- Manejo de secretos/configuración vía variables de entorno gestionadas
  (no hardcodeadas), y despliegue containerizado (Docker) para reproducibilidad
  del entorno (especialmente la dependencia del binario de Tesseract).
- Monitoreo de deriva de precisión: si se migra a un modelo como GLM-OCR o un
  LLM, versionar prompts/modelos y tener un set de regresión para detectar
  degradación de calidad entre versiones.

## Testing

```bash
cd backend
pytest -v
```

Ver [`backend/tests/fixtures/README.md`](backend/tests/fixtures/README.md) para
el detalle de los documentos de prueba (sintéticos y reales anonimizados).
