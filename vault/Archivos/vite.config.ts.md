**Ruta:** `vite.config.ts`

## Responsabilidad
Config de Vite (dev server + build) y de vitest. Plugins React, Tailwind y vite-plugin-pwa.

## Contenido clave
- `plugins`: `react()`, `tailwindcss()`, `vite-plugin-pwa` (injectManifest: `src/sw.ts`)
- `server`: host `127.0.0.1`, puerto **5174**, proxy `"/api" -> http://127.0.0.1:8001`
- `test` (vitest): `environment: "node"`, `include: ["src/**/*.test.ts"]`
- PWA: `injectManifest` mode, `registerSW.js` disabled (custom PWA provider), SW output `sw.js`

## Importa
- Librerías externas: `vitest/config`, `@vitejs/plugin-react`, `@tailwindcss/vite`, `vite-plugin-pwa`

## Importado por
- Toolchain Vite/vitest
