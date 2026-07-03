**Ruta:** `playwright.config.ts`

## Responsabilidad
Config de Playwright para los tests e2e. Levanta automáticamente backend + frontend y aísla la DB para no tocar la de desarrollo.

## Contenido clave
- `testDir: "./e2e"`, `fullyParallel: false`, `workers: 1` (serial a propósito: los tests comparten una única DB SQLite)
- `baseURL: http://127.0.0.1:5174`, proyecto chromium
- `webServer[0]` (API): `rm -rf e2e/.db && mkdir -p e2e/.db && npm run dev:api`, con `NODEBOARD_DB=sqlite:///./e2e/.db/nodeboard.test.db`; espera `/docs`; `reuseExistingServer: false` (nunca pega contra la DB de dev)
- `webServer[1]` (web): `npm run dev:web`, espera `:5174`

## Importa
- Librerías externas: `@playwright/test`

## Importado por
- Toolchain Playwright; usa [[../Archivos/package.json.md]] (`dev:api`, `dev:web`) y los specs de [[../Archivos/e2e/helpers.ts.md]]
