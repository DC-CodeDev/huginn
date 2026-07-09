import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { connectPorts, createCardNodeAndGetId, dragNodeBy, setupStudioAndBoard } from "./helpers";

test("exporta el board completo como PNG 3x aunque los nodos esten fuera del viewport", async ({ page }) => {
  await setupStudioAndBoard(page);

  const idA = await createCardNodeAndGetId(page);
  const idB = await createCardNodeAndGetId(page);
  await dragNodeBy(page, idB, 520, 220);

  const aPorts = page.locator(`[data-testid="${idA}"] [data-testid^="port-"]`);
  const bPorts = page.locator(`[data-testid="${idB}"] [data-testid^="port-"]`);
  const aOut = await aPorts.nth(1).getAttribute("data-testid");
  const bIn = await bPorts.nth(0).getAttribute("data-testid");
  await connectPorts(page, aOut!, bIn!);

  const canvasBox = await page.getByTestId("board-canvas").boundingBox();
  if (!canvasBox) throw new Error("no se pudo ubicar el canvas");

  const startX = canvasBox.x + canvasBox.width - 80;
  const startY = canvasBox.y + canvasBox.height - 80;
  for (let i = 0; i < 2; i += 1) {
    await page.mouse.move(startX, startY);
    await page.mouse.down();
    await page.mouse.move(startX - 900, startY - 320, { steps: 14 });
    await page.mouse.up();
  }

  await expect(page.locator(`[data-testid="${idA}"]`)).not.toBeInViewport();
  await expect(page.locator(`[data-testid="${idB}"]`)).not.toBeInViewport();

  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("export-png").click();
  const download = await downloadPromise;

  expect(download.suggestedFilename()).toMatch(/\.png$/);
  const filePath = await download.path();
  if (!filePath) throw new Error("Playwright no devolvio path para la descarga");

  const png = await readFile(filePath);
  const { width, height } = readPngDimensions(png);

  expect(width).toBeGreaterThan(2500);
  expect(height).toBeGreaterThan(900);
  expect(width % 3).toBe(0);
  expect(height % 3).toBe(0);
});

function readPngDimensions(buffer: Buffer) {
  expect(buffer.subarray(0, 8)).toEqual(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));

  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}
