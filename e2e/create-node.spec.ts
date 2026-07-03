import { test, expect } from "@playwright/test";
import { waitForBoardLoaded } from "./helpers";

test("crear un nodo card aumenta la cantidad de nodos en uno", async ({ page }) => {
  await page.goto("/");
  await waitForBoardLoaded(page);

  const nodes = page.locator('[data-testid^="node-"]');
  const before = await nodes.count();

  await page.getByTestId("add-node-card").click();

  await expect(nodes).toHaveCount(before + 1);
});
