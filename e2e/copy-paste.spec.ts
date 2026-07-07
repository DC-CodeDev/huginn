import { test, expect } from "@playwright/test";
import { createCardNodeAndGetId, setupStudioAndBoard, dragNodeBy } from "./helpers";

/**
 * Obtiene el id de los nodos recién aparecidos entre dos snapshots de testids.
 */
function findNewIds(before: (string | null)[], after: (string | null)[]): string[] {
  const beforeSet = new Set(before);
  return after.filter((id): id is string => id !== null && !beforeSet.has(id));
}

test("Ctrl+C + Ctrl+V crea nodo con mismo contenido, sin edges nuevas, en posición offset; segundo paste acumula offset", async ({ page }) => {
  await setupStudioAndBoard(page);

  // Crear el nodo que será copiado y darle un título único para identificarlo.
  const originalId = await createCardNodeAndGetId(page);
  await page.locator(`[data-testid="${originalId}"] input`).first().fill("CopyPasteTest");
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 5_000 });

  // Contar aristas del canvas (usando el SVG específico para no incluir íconos de la UI).
  const edgesLocator = page.locator("[data-testid='canvas-edges'] path:not([stroke='transparent'])");
  const edgesBefore = await edgesLocator.count();

  // Seleccionar el nodo haciendo click en el dot del encabezado (un span, no un input).
  // Esto dispara onStartDrag → setSelection sin dar foco a ningún input, garantizando que
  // el handler de teclado no haga early-return cuando se presione Ctrl+C.
  await page.locator(`[data-testid="${originalId}"] span.rounded-full`).first().click();

  // Esperar a que la barra de selección aparezca: confirma que `selection` está activo en React.
  await expect(page.getByRole("button", { name: "Eliminar" })).toBeVisible({ timeout: 3_000 });

  // Copiar.
  await page.keyboard.press("Control+c");

  // --- Primer paste ---
  const idsBefore1 = await page.locator('[data-testid^="node-"]').evaluateAll(
    (els) => els.map((el) => el.getAttribute("data-testid")),
  );
  await page.keyboard.press("Control+v");
  // Esperar que el nodo aparezca en el DOM (setNodes es síncrono) y luego el autosave.
  await expect(page.locator('[data-testid^="node-"]')).toHaveCount(idsBefore1.length + 1, { timeout: 3_000 });
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 5_000 });

  const idsAfter1 = await page.locator('[data-testid^="node-"]').evaluateAll(
    (els) => els.map((el) => el.getAttribute("data-testid")),
  );
  const [pasted1Id] = findNewIds(idsBefore1, idsAfter1);

  // El nodo pegado tiene el mismo título que el original.
  await expect(page.locator(`[data-testid="${pasted1Id}"] input`).first()).toHaveValue("CopyPasteTest");

  // No se crearon aristas nuevas.
  await expect(edgesLocator).toHaveCount(edgesBefore);

  // La posición del nodo pegado es offset +20,+20 respecto al original.
  const origX = parseFloat((await page.locator(`[data-testid="${originalId}"]`).getAttribute("data-node-x"))!);
  const origY = parseFloat((await page.locator(`[data-testid="${originalId}"]`).getAttribute("data-node-y"))!);
  const p1X = parseFloat((await page.locator(`[data-testid="${pasted1Id}"]`).getAttribute("data-node-x"))!);
  const p1Y = parseFloat((await page.locator(`[data-testid="${pasted1Id}"]`).getAttribute("data-node-y"))!);

  expect(p1X).toBeCloseTo(origX + 20, 0);
  expect(p1Y).toBeCloseTo(origY + 20, 0);

  // --- Segundo paste: offset acumulado sobre el primer paste, no sobre el original ---
  // El nodo pegado queda seleccionado; el clipboard sigue activo.
  const idsBefore2 = await page.locator('[data-testid^="node-"]').evaluateAll(
    (els) => els.map((el) => el.getAttribute("data-testid")),
  );
  await page.keyboard.press("Control+v");
  await expect(page.locator('[data-testid^="node-"]')).toHaveCount(idsBefore2.length + 1, { timeout: 3_000 });
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 5_000 });

  const idsAfter2 = await page.locator('[data-testid^="node-"]').evaluateAll(
    (els) => els.map((el) => el.getAttribute("data-testid")),
  );
  const [pasted2Id] = findNewIds(idsBefore2, idsAfter2);

  const p2X = parseFloat((await page.locator(`[data-testid="${pasted2Id}"]`).getAttribute("data-node-x"))!);
  const p2Y = parseFloat((await page.locator(`[data-testid="${pasted2Id}"]`).getAttribute("data-node-y"))!);

  expect(p2X).toBeCloseTo(p1X + 20, 0);
  expect(p2Y).toBeCloseTo(p1Y + 20, 0);
});

test("Ctrl+C con multiples nodos seleccionados preserva posiciones relativas y no crea edges entre copias", async ({ page }) => {
  await setupStudioAndBoard(page);

  // Crear dos nodos y separarlos para que tengan posiciones distintas
  const id1 = await createCardNodeAndGetId(page);
  await dragNodeBy(page, id1, 300, 0);
  const id2 = await createCardNodeAndGetId(page);
  await dragNodeBy(page, id2, 0, 150);

  // Seleccionar ambos con shift+click
  await page.locator(`[data-testid="${id1}"] span.rounded-full`).first().click();
  await page.locator(`[data-testid="${id2}"] span.rounded-full`).first().click({ modifiers: ["Shift"] });
  await expect(page.locator(`[data-testid="${id1}"]`)).toHaveAttribute("data-selected", "true");
  await expect(page.locator(`[data-testid="${id2}"]`)).toHaveAttribute("data-selected", "true");

  // Guardar posiciones originales (coordenadas mundo)
  const x1 = parseFloat((await page.locator(`[data-testid="${id1}"]`).getAttribute("data-node-x"))!);
  const y1 = parseFloat((await page.locator(`[data-testid="${id1}"]`).getAttribute("data-node-y"))!);
  const x2 = parseFloat((await page.locator(`[data-testid="${id2}"]`).getAttribute("data-node-x"))!);
  const y2 = parseFloat((await page.locator(`[data-testid="${id2}"]`).getAttribute("data-node-y"))!);

  const edgesLocator = page.locator("[data-testid='canvas-edges'] path:not([stroke='transparent'])");
  const edgesBefore = await edgesLocator.count();

  const idsBefore = await page.locator('[data-testid^="node-"]').evaluateAll(
    (els) => els.map((el) => el.getAttribute("data-testid")),
  );

  await page.keyboard.press("Control+c");
  await page.keyboard.press("Control+v");

  // Deben aparecer exactamente 2 nodos nuevos
  await expect(page.locator('[data-testid^="node-"]')).toHaveCount(idsBefore.length + 2, { timeout: 3_000 });
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 5_000 });

  const idsAfter = await page.locator('[data-testid^="node-"]').evaluateAll(
    (els) => els.map((el) => el.getAttribute("data-testid")),
  );
  const beforeSet = new Set(idsBefore);
  const newIds = idsAfter.filter((id): id is string => id !== null && !beforeSet.has(id));
  expect(newIds).toHaveLength(2);

  // Sin edges nuevas (incluyendo entre las copias)
  await expect(edgesLocator).toHaveCount(edgesBefore);

  // Los dos nodos pegados quedan seleccionados (barra visible)
  await expect(page.getByRole("button", { name: "Eliminar" })).toBeVisible();

  // Leer posiciones de las copias (newIds[0] = copia de id1, newIds[1] = copia de id2,
  // porque clipboard mantiene el orden del array nodes que tiene id1 antes que id2)
  const px1 = parseFloat((await page.locator(`[data-testid="${newIds[0]}"]`).getAttribute("data-node-x"))!);
  const py1 = parseFloat((await page.locator(`[data-testid="${newIds[0]}"]`).getAttribute("data-node-y"))!);
  const px2 = parseFloat((await page.locator(`[data-testid="${newIds[1]}"]`).getAttribute("data-node-x"))!);
  const py2 = parseFloat((await page.locator(`[data-testid="${newIds[1]}"]`).getAttribute("data-node-y"))!);

  // Cada copia está offset +20,+20 respecto a su original
  expect(px1).toBeCloseTo(x1 + 20, 0);
  expect(py1).toBeCloseTo(y1 + 20, 0);
  expect(px2).toBeCloseTo(x2 + 20, 0);
  expect(py2).toBeCloseTo(y2 + 20, 0);

  // Distancia relativa entre las copias = distancia relativa entre los originales
  expect(px2 - px1).toBeCloseTo(x2 - x1, 0);
  expect(py2 - py1).toBeCloseTo(y2 - y1, 0);
});
