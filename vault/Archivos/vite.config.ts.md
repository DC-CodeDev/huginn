**Ruta:** `vite.config.ts`

## Responsabilidad
Config de Vite (dev server + build) y de vitest. Plugins React y Tailwind.

## Contenido clave
- `plugins`: `react()`, `tailwindcss()`
- `server`: host `127.0.0.1`, puerto **5174**, proxy `"/api" → http://127.0.0.1:8001` (redirige al backend en dev; por eso el frontend puede usar `BASE=""`)
- `test` (vitest): `environment: "node"`, `include: ["src/**/*.test.ts"]`

## Importa
- Librerías externas: `vitest/config`, `@vitejs/plugin-react`, `@tailwindcss/vite`

## Importado por
- Toolchain Vite/vitest
