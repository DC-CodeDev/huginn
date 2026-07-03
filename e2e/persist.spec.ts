import { test, expect } from "@playwright/test";
import { waitForBoardLoaded } from "./helpers";

test("un nodo creado persiste tras recargar la página", async ({ page }) => {
  await page.goto("/");
  await waitForBoardLoaded(page);

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

  await page.reload();
  await waitForBoardLoaded(page);

  await expect(page.locator(`[data-testid="${newNodeId}"]`)).toBeVisible();
});
