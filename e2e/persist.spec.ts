import { test, expect } from "@playwright/test";
import { setupStudioAndBoard } from "./helpers";

test("un nodo creado persiste tras recargar la página", async ({ page }) => {
  await setupStudioAndBoard(page);

  const nodes = page.locator('[data-testid^="node-"]');
  const idsBefore = await nodes.evaluateAll((els) =>
    els.map((el) => el.getAttribute("data-testid")),
  );

  // Creamos un nodo y esperamos a que el autosave (debounce 800ms) haga el PUT.
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/state") && r.request().method() === "PUT" && r.ok(),
      { timeout: 10_000 },
    ),
    page.getByTestId("add-node-card").click(),
  ]);
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 5_000 });

  // Identificamos el testid del nodo recién creado (el que no estaba antes).
  const idsAfter = await nodes.evaluateAll((els) =>
    els.map((el) => el.getAttribute("data-testid")),
  );
  const newNodeId = idsAfter.find((id) => !idsBefore.includes(id));
  expect(newNodeId, "debería haber un nodo nuevo respecto al estado inicial").toBeTruthy();

  // Recargar → vuelve al Home. Navegar de vuelta al board.
  await page.reload();
  // Home → click en el primer Studio
  await expect(page.getByTestId(/^studio-card-/).first()).toBeVisible({ timeout: 5_000 });
  await page.getByTestId(/^studio-card-/).first().click();
  // Studio view → click en el primer board (recientes)
  await expect(page.getByTestId(/^board-card-/).first()).toBeVisible({ timeout: 5_000 });
  await page.getByTestId(/^board-card-/).first().click();
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 15_000 });

  await expect(page.locator(`[data-testid="${newNodeId}"]`)).toBeVisible();
});
