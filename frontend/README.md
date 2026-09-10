# Extractor de Facturas ARCA — Frontend

Frontend de una sola página para el extractor de datos de facturas ARCA/AFIP. Permite subir un archivo (PDF o imagen), enviarlo al backend y visualizar el resultado de la extracción: datos estructurados, nivel de confianza por campo, advertencias y errores.

## Cómo correrlo

```bash
npm install
cp .env.local.example .env.local
npm run dev
```

La app queda disponible en [http://localhost:3000](http://localhost:3000).

## Requisitos

Este frontend necesita el backend corriendo en `http://localhost:8000` (o en la URL indicada por la variable de entorno `NEXT_PUBLIC_API_URL` en `.env.local`).

Para el contexto completo del proyecto (diseño, backend, decisiones y limitaciones), ver el README en la raíz del repositorio.
