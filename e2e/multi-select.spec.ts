import { test, expect, type Page } from "@playwright/test";
import { createCardNodeAndGetId, setupStudioAndBoard, dragNodeBy } from "./helpers";

/**
 * Selecciona un nodo haciendo click en su dot (span.rounded-full) para evitar
 * dar foco a un input, garantizando que el handler de teclado no haga early-return.
 */
async function clickNode(page: Page, testId: string, opts?: { shift?: boolean; ctrl?: boolean }) {
  const modifiers: ("Shift" | "Control")[] = [];
  if (opts?.shift) modifiers.push("Shift");
  if (opts?.ctrl) modifiers.push("Control");
  await page.locator(`[data-testid="${testId}"] span.rounded-full`).first().click(
    modifiers.length ? { modifiers } : undefined
  );
}

test("shift+click agrega y quita nodos de la seleccion", async ({ page }) => {
  await setupStudioAndBoard(page);

  const id1 = await createCardNodeAndGetId(page);
  await dragNodeBy(page, id1, 300, 0);
  const id2 = await createCardNodeAndGetId(page);

  // Click simple en nodo 1 → solo nodo 1 seleccionado
  await clickNode(page, id1);
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "true");
  await expect(page.locator(`[data-testid="${id2}"]`)).toHaveAttribute("data-selected", "false");

  // Shift+click en nodo 2 → ambos seleccionados
  await clickNode(page, id2, { shift: true });
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "true");
  await expect(page.locator(`[data-testid="${id2}"]`)).toHaveAttribute("data-selected", "true");

  // La barra de selección sigue visible
  await expect(page.getByRole("button", { name: "Eliminar" })).toBeVisible();

  // Shift+click en nodo 2 de nuevo → lo quita, nodo 1 sigue seleccionado
  await clickNode(page, id2, { shift: true });
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "true");
  await expect(page.locator(`[data-testid="${id2}"]`)).toHaveAttribute("data-selected", "false");
});

test("ctrl+click agrega y quita nodos de la seleccion", async ({ page }) => {
  await setupStudioAndBoard(page);

  const id1 = await createCardNodeAndGetId(page);
  await dragNodeBy(page, id1, 300, 0);
  const id2 = await createCardNodeAndGetId(page);

  await clickNode(page, id1);
  await clickNode(page, id2, { ctrl: true });

  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "true");
  await expect(page.locator(`[data-testid="${id2}"]`)).toHaveAttribute("data-selected", "true");

  await clickNode(page, id1, { ctrl: true });
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "false");
  await expect(page.locator(`[data-testid="${id2}"]`)).toHaveAttribute("data-selected", "true");
});

test("click simple reemplaza toda la seleccion existente", async ({ page }) => {
  await setupStudioAndBoard(page);

  const id1 = await createCardNodeAndGetId(page);
  await dragNodeBy(page, id1, 300, 0);
  const id2 = await createCardNodeAndGetId(page);

  // Construir seleccion multiple
  await clickNode(page, id1);
  await clickNode(page, id2, { shift: true });
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "true");
  await expect(page.locator(`[data-testid="${id2}"]`)).toHaveAttribute("data-selected", "true");

  // Click simple en nodo 1 → reemplaza; solo nodo 1
  await clickNode(page, id1);
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "true");
  await expect(page.locator(`[data-testid="${id2}"]`)).toHaveAttribute("data-selected", "false");
});

test("click en canvas vacio deselecciona todo", async ({ page }) => {
  await setupStudioAndBoard(page);

  const id1 = await createCardNodeAndGetId(page);
  await clickNode(page, id1);
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "true");

  // Click en el fondo del canvas (coordenada arbitraria fuera de cualquier nodo)
  await page.mouse.click(5, 5);
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "false");
  await expect(page.getByRole("button", { name: "Eliminar" })).not.toBeVisible();
});

test("arrastrar un nodo de una seleccion multiple mueve todo el grupo manteniendo distancias relativas", async ({ page }) => {
  await setupStudioAndBoard(page);

  const id1 = await createCardNodeAndGetId(page);
  await dragNodeBy(page, id1, 300, 0);
  const id2 = await createCardNodeAndGetId(page);
  await dragNodeBy(page, id2, 0, 150);

  // Seleccionar ambos nodos
  await clickNode(page, id1);
  await clickNode(page, id2, { shift: true });
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "true");
  await expect(page.locator(`[data-testid="${id2}"]`)).toHaveAttribute("data-selected", "true");

  // Guardar posiciones antes del arrastre
  const x1Before = parseFloat((await page.locator(`[data-testid="${id1}"]`).getAttribute("data-node-x"))!);
  const y1Before = parseFloat((await page.locator(`[data-testid="${id1}"]`).getAttribute("data-node-y"))!);
  const x2Before = parseFloat((await page.locator(`[data-testid="${id2}"]`).getAttribute("data-node-x"))!);
  const y2Before = parseFloat((await page.locator(`[data-testid="${id2}"]`).getAttribute("data-node-y"))!);

  // Arrastrar el nodo id1 (que está en la selección) por (50, 60) píxeles
  await dragNodeBy(page, id1, 50, 60);

  // Leer posiciones después del arrastre
  const x1After = parseFloat((await page.locator(`[data-testid="${id1}"]`).getAttribute("data-node-x"))!);
  const y1After = parseFloat((await page.locator(`[data-testid="${id1}"]`).getAttribute("data-node-y"))!);
  const x2After = parseFloat((await page.locator(`[data-testid="${id2}"]`).getAttribute("data-node-x"))!);
  const y2After = parseFloat((await page.locator(`[data-testid="${id2}"]`).getAttribute("data-node-y"))!);

  // Ambos nodos se movieron (ninguno quedó estático)
  expect(Math.abs(x1After - x1Before)).toBeGreaterThan(1);
  expect(Math.abs(x2After - x2Before)).toBeGreaterThan(1);

  // La distancia relativa entre ellos es la misma después del arrastre
  expect(x2After - x1After).toBeCloseTo(x2Before - x1Before, 0);
  expect(y2After - y1After).toBeCloseTo(y2Before - y1Before, 0);

  // Ambos nodos se movieron por el mismo delta
  expect(x1After - x1Before).toBeCloseTo(x2After - x2Before, 0);
  expect(y1After - y1Before).toBeCloseTo(y2After - y2Before, 0);
});

test("arrastrar un nodo que NO esta en una seleccion multiple no mueve el resto", async ({ page }) => {
  await setupStudioAndBoard(page);

  const id1 = await createCardNodeAndGetId(page);
  await dragNodeBy(page, id1, 300, 0);
  const id2 = await createCardNodeAndGetId(page);
  await dragNodeBy(page, id2, 0, 150);

  // Seleccionar solo id2 (seleccion simple, id1 queda fuera)
  await clickNode(page, id2);
  await expect(page.locator(`[data-testid="${id2}"]`)).toHaveAttribute("data-selected", "true");
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "false");

  // Capturar posiciones antes del arrastre
  const x1Before = parseFloat((await page.locator(`[data-testid="${id1}"]`).getAttribute("data-node-x"))!);
  const x2Before = parseFloat((await page.locator(`[data-testid="${id2}"]`).getAttribute("data-node-x"))!);
  const y2Before = parseFloat((await page.locator(`[data-testid="${id2}"]`).getAttribute("data-node-y"))!);

  // Arrastrar id1, que no está en la selección activa
  await dragNodeBy(page, id1, 80, 0);

  const x1After = parseFloat((await page.locator(`[data-testid="${id1}"]`).getAttribute("data-node-x"))!);
  const x2After = parseFloat((await page.locator(`[data-testid="${id2}"]`).getAttribute("data-node-x"))!);
  const y2After = parseFloat((await page.locator(`[data-testid="${id2}"]`).getAttribute("data-node-y"))!);

  // id1 se movió
  expect(Math.abs(x1After - x1Before)).toBeGreaterThan(1);

  // id2 no se movió
  expect(x2After).toBeCloseTo(x2Before, 0);
  expect(y2After).toBeCloseTo(y2Before, 0);
});
