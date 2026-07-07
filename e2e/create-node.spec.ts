import { test, expect } from "@playwright/test";
import { setupStudioAndBoard } from "./helpers";

test("crear un nodo card aumenta la cantidad de nodos en uno", async ({ page }) => {
  await setupStudioAndBoard(page);

  const nodes = page.locator('[data-testid^="node-"]');
  const before = await nodes.count();

  await page.getByTestId("add-node-card").click();

  await expect(nodes).toHaveCount(before + 1);
});
