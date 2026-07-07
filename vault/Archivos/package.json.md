**Ruta:** `package.json`

## Responsabilidad
Manifiesto del frontend + orquestacion de dev/test del monorepo (frontend Vite + backend uvicorn via `concurrently`).

## Scripts
- `dev` — `concurrently` de `dev:api` + `dev:web`
- `dev:web` — `vite` (puerto 5174)
- `dev:api` — uvicorn `app.main:app` en :8001 con `NODEBOARD_DB` (default `sqlite:///./nodeboard-backend/nodeboard.db`), venv `nodeboard-backend/.venv`
- `build` — `tsc -b && vite build`
- `test` — `vitest`
- `test:api` — pytest en `nodeboard-backend/tests`

## Dependencias PWA anadidas
- `vite-plugin-pwa` ^1.3.0 — build del service worker via `injectManifest`
- `workbox-window` ^7.4.1 — registro del SW y deteccion de update `waiting`

## Dependencias de produccion
- `react`, `react-dom`, `lucide-react`

## Dependencias de desarrollo
- `@types/react`, `@types/react-dom`, `typescript`, `vite`, `@vitejs/plugin-react`, `@tailwindcss/vite`, `tailwindcss`
- `vitest`, `playwright`
- `vite-plugin-pwa`, `workbox-window`, `workbox-precaching`, `workbox-routing`, `workbox-strategies`

## Importado por
- Toolchain Vite
- Dockerfile (copia `package.json`)
