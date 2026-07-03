import { test, expect } from "@playwright/test";
import { connectPorts, createCardNodeAndGetId, waitForBoardLoaded } from "./helpers";

/**
 * Detección de la arista: las aristas no tienen data-testid, así que se usa un
 * selector estructural — cada arista se renderiza como un <g> dentro del
 * <svg width="1"> de conexiones (decisión acordada).
 *
 * Puertos: initialNodes no se renderiza (el board se carga desde la DB), así
 * que se crean dos nodos card nuevos. Como el botón addNode los coloca en la
 * misma posición, se arrastra el segundo para separarlos y poder clickear los
 * puertos de ambos sin solapamiento. Los nodos nuevos se pintan por encima de
 * los de la DB, de modo que sus puertos quedan siempre accesibles.
 */
test("conectar A.out con B.in agrega una arista visible", async ({ page }) => {
  await page.goto("/");
  await waitForBoardLoaded(page);

  const idA = await createCardNodeAndGetId(page);
  const idB = await createCardNodeAndGetId(page); // apilado sobre A

  // Separar B arrastrándolo desde el borde izquierdo de su encabezado (zona sin
  // campos de formulario, que dispara el drag del nodo, no un pan del lienzo).
  const boxB = await page.locator(`[data-testid="${idB}"]`).boundingBox();
  if (!boxB) throw new Error("no se pudo obtener la posición del nodo B");
  const handleX = boxB.x + 6;
  const handleY = boxB.y + 20;
  await page.mouse.move(handleX, handleY);
  await page.mouse.down();
  await page.mouse.move(handleX + 360, handleY + 200, { steps: 12 });
  await page.mouse.up();

  // Dots de puerto en orden de node.ports: [0] = "in" (left), [1] = "out" (right).
  const aPorts = page.locator(`[data-testid="${idA}"] [data-testid^="port-"]`);
  const bPorts = page.locator(`[data-testid="${idB}"] [data-testid^="port-"]`);
  const aOut = await aPorts.nth(1).getAttribute("data-testid");
  const bIn = await bPorts.nth(0).getAttribute("data-testid");

  const edges = page.locator('svg[width="1"] > g');
  const edgesBefore = await edges.count();

  await connectPorts(page, aOut!, bIn!);

  await expect(edges).toHaveCount(edgesBefore + 1);
});
