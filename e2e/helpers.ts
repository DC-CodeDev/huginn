import { expect, type Page } from "@playwright/test";

/**
 * Conecta dos puertos siguiendo el mecanismo real de la app: click en el
 * puerto origen (inicia la conexión) y luego click en el puerto destino
 * (la termina). NO es drag ni mousedown/mouseup continuo — el handler real
 * de los dots es `onClick` (ver NodeCard.tsx / onPortClick en NodeBoard.tsx).
 *
 * @param page        Página de Playwright.
 * @param fromTestId  data-testid del puerto origen (ej. "port-<nodeId>-<portId>").
 * @param toTestId    data-testid del puerto destino.
 */
export async function connectPorts(page: Page, fromTestId: string, toTestId: string) {
  await page.getByTestId(fromTestId).click();
  await page.getByTestId(toTestId).click();
}

/**
 * Espera a que el board termine de cargar desde el backend. El hook de
 * persistencia arranca en "cargando" y pasa a "guardado" cuando el fetch
 * inicial resuelve; sólo entonces el estado en pantalla refleja la DB.
 */
export async function waitForBoardLoaded(page: Page) {
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 15_000 });
}

/**
 * Hace click en "add-node-card" y devuelve el data-testid del nodo recién
 * creado, identificado por diferencia contra los nodos previos. Robusto frente
 * al estado acumulado de la DB: no asume un conteo absoluto ni ids fijos.
 */
export async function createCardNodeAndGetId(page: Page): Promise<string> {
  const nodes = page.locator('[data-testid^="node-"]');
  const before = await nodes.evaluateAll((els) => els.map((el) => el.getAttribute("data-testid")));

  await page.getByTestId("add-node-card").click();
  await expect(nodes).toHaveCount(before.length + 1);

  const after = await nodes.evaluateAll((els) => els.map((el) => el.getAttribute("data-testid")));
  const created = after.find((id) => !before.includes(id));
  if (!created) throw new Error("no se pudo identificar el nodo recién creado");
  return created;
}
