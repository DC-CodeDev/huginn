import { defineConfig, devices } from "@playwright/test";

/**
 * Config de Playwright para Huginn.
 *
 * Levanta automáticamente el dev server antes de correr los tests. Se usan dos
 * entradas de webServer en lugar de `npm run dev` (concurrently) para que
 * Playwright espere a que TANTO la API (8001) como el frontend (5174) estén
 * listos: el Test de persistencia necesita el backend arriba antes de navegar.
 *
 * Ejecución serial (workers: 1) a propósito: los tests comparten una única DB
 * SQLite en el backend, así que correrlos en paralelo produciría carreras de
 * estado. Cada test verifica su propio delta, no un conteo absoluto.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      // DB aislada para e2e: se resetea ANTES de arrancar uvicorn (Playwright
      // levanta el webServer antes que globalSetup, así que borrar el archivo
      // desde un globalSetup correría carrera con la API ya abierta). El
      // `NODEBOARD_DB` de acá sobreescribe el default de dev:api sin afectar el
      // desarrollo normal (donde la variable no está seteada).
      command: "rm -rf e2e/.db && mkdir -p e2e/.db && npm run dev:api",
      url: "http://127.0.0.1:8001/docs",
      env: { NODEBOARD_DB: "sqlite:///./e2e/.db/nodeboard.test.db" },
      // Nunca reutilizar un server preexistente en 8001 (ni en CI ni en local):
      // si Playwright reusara un `npm run dev` de desarrollo, los tests pegarían
      // contra la DB de dev y se perdería el aislamiento. Con `false`, si el
      // puerto está ocupado Playwright aborta con un error claro en vez de
      // correr contra un backend ajeno; con el puerto libre levanta el suyo
      // propio apuntando a la DB de test.
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "npm run dev:web",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
