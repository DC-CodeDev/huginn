import { test, expect } from "@playwright/test";
import { connectPorts, createCardNodeAndGetId, setupStudioAndBoard } from "./helpers";

/**
 * Verifica que las edges seleccionadas se puedan eliminar sin afectar nodos.
 *
 * Las edges se renderizan como <g> dentro del <svg width="1"> de conexiones.
 * La selección se hace clickeando el path invisible encima de la edge.
 * No hay data-testid en las edges — el conteo es por cantidad de <g> hijos.
 */
test("Delete elimina la edge seleccionada sin afectar nodos", async ({ page }) => {
  await setupStudioAndBoard(page);

  const idA = await createCardNodeAndGetId(page);
  const idB = await createCardNodeAndGetId(page);

  // Separar B arrastrándolo
  const boxB = await page.locator(`[data-testid="${idB}"]`).boundingBox();
  if (!boxB) throw new Error("no se pudo ubicar B");
  await page.mouse.move(boxB.x + 6, boxB.y + 20);
  await page.mouse.down();
  await page.mouse.move(boxB.x + 360, boxB.y + 200, { steps: 12 });
  await page.mouse.up();

  // Conectar A.out → B.in
  const aPorts = page.locator(`[data-testid="${idA}"] [data-testid^="port-"]`);
  const bPorts = page.locator(`[data-testid="${idB}"] [data-testid^="port-"]`);
  const aOut = await aPorts.nth(1).getAttribute("data-testid");
  const bIn = await bPorts.nth(0).getAttribute("data-testid");
  if (!aOut || !bIn) throw new Error("no se encontraron puertos");

  const edges = page.locator('svg[width="1"] > g');
  const edgesBefore = await edges.count();
  await connectPorts(page, aOut, bIn);
  await expect(edges).toHaveCount(edgesBefore + 1);

  // Seleccionar la edge clickeando el path invisible sobre la arista
  const edgeGroup = edges.last();
  const invisiblePath = edgeGroup.locator("path").first();
  await invisiblePath.click();

  // Debería aparecer la barra de acciones con "Eliminar"
  await expect(page.getByRole("button", { name: "Eliminar", exact: true })).toBeVisible();

  // Pulsar Delete
  await page.keyboard.press("Delete");
  await expect(edges).toHaveCount(edgesBefore);

  // Los nodos deben seguir existiendo
  await expect(page.locator(`[data-testid="${idA}"]`)).toBeVisible();
  await expect(page.locator(`[data-testid="${idB}"]`)).toBeVisible();
});

test("Botón Eliminar en barra de acción remueve la edge seleccionada sin tocar nodos", async ({ page }) => {
  await setupStudioAndBoard(page);

  const idA = await createCardNodeAndGetId(page);
  const idB = await createCardNodeAndGetId(page);

  // Separar B
  const boxB = await page.locator(`[data-testid="${idB}"]`).boundingBox();
  if (!boxB) throw new Error("no se pudo ubicar B");
  await page.mouse.move(boxB.x + 6, boxB.y + 20);
  await page.mouse.down();
  await page.mouse.move(boxB.x + 360, boxB.y + 200, { steps: 12 });
  await page.mouse.up();

  // Conectar
  const aPorts = page.locator(`[data-testid="${idA}"] [data-testid^="port-"]`);
  const bPorts = page.locator(`[data-testid="${idB}"] [data-testid^="port-"]`);
  const aOut = await aPorts.nth(1).getAttribute("data-testid");
  const bIn = await bPorts.nth(0).getAttribute("data-testid");
  if (!aOut || !bIn) throw new Error("no se encontraron puertos");

  const edges = page.locator('svg[width="1"] > g');
  const edgesBefore = await edges.count();
  await connectPorts(page, aOut, bIn);
  await expect(edges).toHaveCount(edgesBefore + 1);

  // Seleccionar edge
  const edgeGroup = edges.last();
  await edgeGroup.locator("path").first().click();

  // Click en botón Eliminar
  await page.getByRole("button", { name: "Eliminar", exact: true }).click();
  await expect(edges).toHaveCount(edgesBefore);

  // Los nodos NO deben desaparecer
  await expect(page.locator(`[data-testid="${idA}"]`)).toBeVisible();
  await expect(page.locator(`[data-testid="${idB}"]`)).toBeVisible();
});

test("Backspace también elimina la edge seleccionada", async ({ page }) => {
  await setupStudioAndBoard(page);

  const idA = await createCardNodeAndGetId(page);
  const idB = await createCardNodeAndGetId(page);

  const boxB = await page.locator(`[data-testid="${idB}"]`).boundingBox();
  if (!boxB) throw new Error("no se pudo ubicar B");
  await page.mouse.move(boxB.x + 6, boxB.y + 20);
  await page.mouse.down();
  await page.mouse.move(boxB.x + 360, boxB.y + 200, { steps: 12 });
  await page.mouse.up();

  const aPorts = page.locator(`[data-testid="${idA}"] [data-testid^="port-"]`);
  const bPorts = page.locator(`[data-testid="${idB}"] [data-testid^="port-"]`);
  const aOut = await aPorts.nth(1).getAttribute("data-testid");
  const bIn = await bPorts.nth(0).getAttribute("data-testid");
  if (!aOut || !bIn) throw new Error("no se encontraron puertos");

  const edges = page.locator('svg[width="1"] > g');
  const edgesBefore = await edges.count();
  await connectPorts(page, aOut, bIn);
  await expect(edges).toHaveCount(edgesBefore + 1);

  // Seleccionar edge y presionar Backspace
  await edges.last().locator("path").first().click();
  await page.keyboard.press("Backspace");
  await expect(edges).toHaveCount(edgesBefore);

  // Nodos intactos
  await expect(page.locator(`[data-testid="${idA}"]`)).toBeVisible();
  await expect(page.locator(`[data-testid="${idB}"]`)).toBeVisible();
});
