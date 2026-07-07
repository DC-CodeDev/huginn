# Resumen Etapa 3 — Migración a Railway

> Fecha: 2026-07-07
> Tests: 33/33 pasaron (pytest backend).

---

## Archivos modificados

### `nodeboard-backend/app/main.py`

| Cambio | Líneas | Detalle |
|--------|--------|---------|
| Imports | +2 | `FileResponse` + `StaticFiles` (para servir frontend) |
| CORS | L86-92 | Ahora lee `CORS_ORIGINS` (env var, separado por comas). Fallback a `localhost:5174,localhost:3000` para no romper dev local |
| Static catch-all | al final | Bloque condicional (solo si existe `static/`): monta `/assets` como estáticos y agrega `/{full_path:path}` que sirve `index.html` para cualquier ruta que no sea `/api/*`. **Orden crítico**: va después de todos los endpoints `/api/*` porque Starlette resuelve por orden de registro |

### `nodeboard-backend/entrypoint.sh` (nuevo)

- Corre `alembic upgrade head`
- Arranca `uvicorn app.main:app` en `$PORT` (fallback `8001`)
- Usa `exec` para que uvicorn herede señales del sistema (SIGTERM de Railway)

### `Dockerfile` (nuevo, raíz del proyecto)

Multi-stage:
- **Builder** (node:22-alpine): `npm ci` + `npm run build` → `dist/`
- **Final** (python:3.12-slim): pip install → copia backend → copia `dist/` a `app/static/` → `mkdir -p /data` → entrypoint.sh
- Build args: `BUILD_COMMIT`, `BUILD_TIMESTAMP`, `VITE_GOOGLE_CLIENT_ID`
- En Railway se setea `DATA_PATH=/data` y se monta un Volume en `/data` para persistir SQLite entre deploys

---

## Variables de entorno nuevas

| Variable | Default | Propósito |
|----------|---------|-----------|
| `CORS_ORIGINS` | `http://localhost:5174,http://127.0.0.1:5174,http://localhost:3000` | Orígenes permitidos por CORS |
| `PORT` | `8001` | Puerto para uvicorn (Railway inyecta `$PORT`) |
| `DATA_PATH` | *(ninguno)* | Ruta absoluta donde se crea `nodeboard.db`. Railway monta un Volume en `DATA_PATH` para persistencia entre deploys |
| `VITE_GOOGLE_CLIENT_ID` | *(requerido)* | Client ID de Google OAuth para build de frontend (build arg) |

---

## No se modificó

- Ninguno de los 25 endpoints `/api/*`
- No se agregaron routers (`app.include_router`)
- No se reestructuró el archivo
- No se tocó lógica de negocio ni modelos
