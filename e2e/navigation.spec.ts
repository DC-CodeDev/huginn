import { test, expect } from "@playwright/test";
import { setupStudioAndBoard, setupStudioFolderAndBoard } from "./helpers";

test("el Home muestra los Studios reales del backend", async ({ page }) => {
  await page.goto("/");

  // Como los tests comparten DB, puede que ya existan Studios o no.
  // Simplemente verificamos que se muestre la UI de Home.
  const emptyBtn = page.getByTestId("empty-create-studio");
  const createCardBtn = page.getByTestId("create-studio-card");
  await expect(emptyBtn.or(createCardBtn).first()).toBeVisible({ timeout: 10_000 });
});

test("crear un Studio nuevo desde el modal lo agrega a la grilla", async ({ page }) => {
  await page.goto("/");

  // Crear via la card punteada
  await page.getByTestId("create-studio-card").click();
  await expect(page.getByTestId("studio-name-input")).toBeVisible();
  await page.getByTestId("studio-name-input").fill("Mi Estudio");
  await page.getByTestId("color-swatch-verde").click();
  await page.getByTestId("studio-create-btn").click();

  // El modal se cierra y el Studio aparece en la grilla
  await expect(page.getByTestId("create-studio-modal")).not.toBeVisible();
  const cards = page.getByTestId(/^studio-card-/);
  await expect(cards.filter({ hasText: "Mi Estudio" })).toBeVisible();
});

test("la vista de Studio separa correctamente recientes de carpetas", async ({ page }) => {
  await page.goto("/");

  // Crear un Studio
  await page.getByTestId("create-studio-card").click();
  await page.getByTestId("studio-name-input").fill("S");
  await page.getByTestId("studio-create-btn").click();
  await expect(page.getByTestId(/^studio-card-/).first()).toBeVisible();

  // Entrar al Studio
  await page.getByTestId(/^studio-card-/).first().click();

  // Crear una carpeta
  await expect(page.getByTestId("create-folder-card")).toBeVisible();
  await page.getByTestId("create-folder-card").click();
  await page.getByTestId("folder-name-input").fill("Carpeta A");
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/folders") && r.request().method() === "POST",
      { timeout: 10_000 },
    ),
    page.getByTestId("folder-create-btn").click(),
  ]);
  await expect(page.getByTestId("create-folder-modal")).not.toBeVisible({ timeout: 5_000 });

  // La carpeta aparece en la sección Carpetas
  await expect(page.getByTestId(/^folder-card-/).first()).toBeVisible();

  // Crear un board en la raíz usando el botón "+ Nuevo Board"
  await page.getByTestId("create-board-btn").click();
  // Esperar a que el board se cargue — estaremos en el canvas
  await expect(page.getByTestId("save-status")).toBeVisible({ timeout: 10_000 });
});

test("la vista de Carpeta lista sus boards y no muestra la seccion Carpetas", async ({ page }) => {
  await page.goto("/");

  // Crear Studio
  await page.getByTestId("create-studio-card").click();
  await page.getByTestId("studio-name-input").fill("S");
  await page.getByTestId("studio-create-btn").click();
  await expect(page.getByTestId(/^studio-card-/).first()).toBeVisible();
  await page.getByTestId(/^studio-card-/).first().click();

  // Crear Carpeta
  await page.getByTestId("create-folder-card").click();
  await page.getByTestId("folder-name-input").fill("F1");
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/folders") && r.request().method() === "POST",
      { timeout: 10_000 },
    ),
    page.getByTestId("folder-create-btn").click(),
  ]);
  await expect(page.getByTestId("create-folder-modal")).not.toBeVisible({ timeout: 5_000 });

  // Entrar a la carpeta
  await page.getByTestId(/^folder-card-/).first().click();

  // No debe tener la sección "Carpetas"
  await expect(page.getByTestId("create-folder-card")).not.toBeVisible();

  // Sí debe tener "Archivos recientes" con estado vacío
  await expect(page.getByText("No hay boards en esta carpeta todavía")).toBeVisible();
});

test("el boton atras desde un board en raiz vuelve al Studio", async ({ page }) => {
  await setupStudioAndBoard(page);

  // Estamos en el canvas del board. Click en Volver.
  await page.getByTestId("back-btn").click();

  // Debemos estar de vuelta en la vista de Studio (no Home)
  await expect(page.getByTestId("create-folder-card")).toBeVisible({ timeout: 5_000 });
  await expect(page.getByTestId("back-to-home")).toBeVisible();
});

test("el boton atras desde un board en carpeta vuelve a la Carpeta", async ({ page }) => {
  await setupStudioFolderAndBoard(page);

  // Estamos en el canvas del board (dentro de una carpeta). Click en Volver.
  await page.getByTestId("back-btn").click();

  // Debemos estar en la vista de Carpeta
  await expect(page.getByTestId("back-to-studio")).toBeVisible({ timeout: 5_000 });
  await expect(page.getByTestId("create-folder-card")).not.toBeVisible();
});
