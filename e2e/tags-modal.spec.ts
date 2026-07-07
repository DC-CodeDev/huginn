import { test, expect } from "@playwright/test";
import {
  createCardNodeAndGetId,
  dragNodeBy,
  openTagsModal,
  setupStudioAndBoard,
  waitForBoardLoaded,
} from "./helpers";

/**
 * Flujo completo del modal de tags (Fase 2):
 *   1. Abrir el modal en un nodo sin tags y crear un tag nuevo → persiste tras recargar.
 *   2. Abrir el modal en otro nodo del mismo tablero → el tag creado aparece como chip sugerido.
 *   3. Filtro en vivo: escribir parcial filtra las sugerencias.
 *   4. Quitar un tag con la X → se guarda (persiste tras recargar).
 *
 * El guardado usa el mismo autosave que el resto de la app (PUT /state debounced),
 * así que cada aserción de persistencia espera ese PUT antes de recargar.
 */

const waitForStatePut = (page: import("@playwright/test").Page) =>
  page.waitForResponse(
    (r) => r.url().includes("/state") && r.request().method() === "PUT" && r.ok(),
    { timeout: 10_000 },
  );

test("crear, persistir, sugerir en otro nodo, filtrar y quitar tags", async ({ page }) => {
  await setupStudioAndBoard(page);

  // Dos nodos card; se separan porque addNode los apila en la misma posición.
  const idA = await createCardNodeAndGetId(page);
  const idB = await createCardNodeAndGetId(page);
  await dragNodeBy(page, idB, 360, 220);
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 5_000 });

  const tag = `qa-${Date.now()}`;

  // 1. Crear un tag nuevo en el nodo A (sin tags) y esperar el autosave.
  await openTagsModal(page, idA);
  await page.getByTestId("tags-input").fill(tag);
  await Promise.all([waitForStatePut(page), page.getByTestId("tags-create").click()]);
  await expect(page.getByTestId(`tag-remove-${tag}`)).toBeVisible();
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 5_000 });

  // Persistencia real: recargar y navegar de vuelta al board, luego reabrir el modal de A.
  await page.reload();
  // Navegar de vuelta: Home → Studio → Board
  await expect(page.getByTestId(/^studio-card-/).first()).toBeVisible({ timeout: 10_000 });
  await page.getByTestId(/^studio-card-/).first().click();
  await expect(page.getByTestId(/^board-card-/).first()).toBeVisible({ timeout: 10_000 });
  await page.getByTestId(/^board-card-/).first().click();
  await waitForBoardLoaded(page);
  await openTagsModal(page, idA);
  await expect(page.getByTestId(`tag-remove-${tag}`)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("tags-input")).toBeHidden();

  // 2. En el nodo B, el tag creado en A aparece como sugerencia del tablero.
  await openTagsModal(page, idB);
  await expect(page.getByTestId(`tag-suggest-${tag}`)).toBeVisible();

  // 3. Filtro en vivo (case-insensitive).
  await page.getByTestId("tags-input").fill(tag.slice(0, 4).toUpperCase());
  await expect(page.getByTestId(`tag-suggest-${tag}`)).toBeVisible();
  await page.getByTestId("tags-input").fill("zzz-no-match");
  await expect(page.getByTestId(`tag-suggest-${tag}`)).toBeHidden();
  await page.getByTestId("tags-input").fill("");

  // Asignar el tag a B haciendo click en la sugerencia, y esperar el autosave.
  await Promise.all([waitForStatePut(page), page.getByTestId(`tag-suggest-${tag}`).click()]);
  await expect(page.getByTestId(`tag-remove-${tag}`)).toBeVisible();
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 5_000 });

  // 4. Quitar el tag de B con la X y confirmar que se guarda y persiste.
  await Promise.all([waitForStatePut(page), page.getByTestId(`tag-remove-${tag}`).click()]);
  await expect(page.getByTestId(`tag-remove-${tag}`)).toBeHidden();
  await expect(page.getByTestId("save-status")).toHaveText("guardado", { timeout: 5_000 });

  await page.reload();
  // Navegar de vuelta al board
  await expect(page.getByTestId(/^studio-card-/).first()).toBeVisible({ timeout: 10_000 });
  await page.getByTestId(/^studio-card-/).first().click();
  await expect(page.getByTestId(/^board-card-/).first()).toBeVisible({ timeout: 10_000 });
  await page.getByTestId(/^board-card-/).first().click();
  await waitForBoardLoaded(page);
  await openTagsModal(page, idB);
  await expect(page.getByTestId(`tag-remove-${tag}`)).toBeHidden();      // ya no asignado a B
  await expect(page.getByTestId(`tag-suggest-${tag}`)).toBeVisible();    // sigue existiendo (nodo A)
});
