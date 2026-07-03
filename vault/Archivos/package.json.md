**Ruta:** `package.json`

## Responsabilidad
Manifiesto del frontend + orquestación de dev/test del monorepo (frontend Vite + backend uvicorn vía `concurrently`).

## Scripts
- `dev` — `concurrently` de `dev:api` + `dev:web`
- `dev:web` — `vite` (puerto 5174)
- `dev:api` — uvicorn `app.main:app` en :8001 con `NODEBOARD_DB` (default `sqlite:///./nodeboard-backend/nodeboard.db`), venv `nodeboard-backend/.venv`
- `build` — `tsc -b && vite build`
- `preview` — `vite preview`
- `test` — `vitest` (unit de `geometry`)
- `test:api` — pytest sobre `nodeboard-backend/tests`

## Dependencias
- runtime: `react`, `react-dom`, `lucide-react`, `@tailwindcss/vite`, `@vitejs/plugin-react`
- dev: `@playwright/test`, `typescript`, `vite`, `vitest`, `tailwindcss`, `concurrently`, tipos React

## Nota
Los tests e2e (Playwright) se corren con `npx playwright test` — no hay script dedicado en `package.json`; la config es [[../Archivos/playwright.config.ts.md]].

## Importado por
- Toolchain (npm) y [[../Archivos/vite.config.ts.md]] / [[../Archivos/playwright.config.ts.md]] (a través de los scripts)
