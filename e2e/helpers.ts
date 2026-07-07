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
 * Abre el modal de tags de un nodo: despliega el menú del nodo (botón "+") y
 * hace click en la entrada "Tags". Recibe el data-testid completo del nodo
 * ("node-<id>") y espera a que el input del modal esté visible.
 */
export async function openTagsModal(page: Page, nodeTestId: string) {
  const id = nodeTestId.replace(/^node-/, "");
  await page.getByTestId(`menu-${id}`).click();
  await page.getByRole("button", { name: "Tags", exact: true }).click();
  await expect(page.getByTestId("tags-input")).toBeVisible();
}

/**
 * Arrastra un nodo por su encabezado (zona sin campos, que dispara el drag del
 * nodo y no un pan del lienzo). Sirve para separar nodos apilados por addNode.
 */
export async function dragNodeBy(page: Page, nodeTestId: string, dx: number, dy: number) {
  const box = await page.locator(`[data-testid="${nodeTestId}"]`).boundingBox();
  if (!box) throw new Error(`no se pudo ubicar el nodo ${nodeTestId}`);
  const x = box.x + 6;
  const y = box.y + 20;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps: 12 });
  await page.mouse.up();
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

/**
 * Navega al canvas de un board partiendo desde Home: crea un Studio via el
 * modal de "Nuevo Estudio", crea un board via el botón "+ Nuevo Board" en la
 * vista del Studio, y espera a que el board esté cargado.
 */
export async function setupStudioAndBoard(page: Page) {
  await page.goto("/");
  // El Home puede estar vacío (empty-create-studio) o tener Studios (create-studio-card).
  // Esperar cualquiera de los dos.
  const emptyBtn = page.getByTestId("empty-create-studio");
  const createBtn = page.getByTestId("create-studio-card");
  await expect(emptyBtn.or(createBtn).first()).toBeVisible({ timeout: 10_000 });

  // Si hay Studios previos, usamos directamente la card punteada "Nuevo Estudio"
  const createCardVisible = await createBtn.isVisible().catch(() => false);
  if (createCardVisible) {
    await createBtn.click();
  } else {
    await emptyBtn.click();
  }
  await expect(page.getByTestId("create-studio-modal")).toBeVisible();
  await page.getByTestId("studio-name-input").fill("Test Studio");
  await page.getByTestId("studio-create-btn").click();
  await expect(page.getByTestId("create-studio-modal")).not.toBeVisible();
  // Esperar que aparezca la card del Studio recién creado
  await expect(page.getByTestId(/^studio-card-/).first()).toBeVisible({ timeout: 5_000 });
  await page.getByTestId(/^studio-card-/).first().click();
  // Studio view — crear board
  await expect(page.getByTestId("create-board-btn")).toBeVisible({ timeout: 5_000 });
  await page.getByTestId("create-board-btn").click();
  // Esperar que el board esté cargado
  await waitForBoardLoaded(page);
}

/**
 * Crea un Studio y una Carpeta, luego un board dentro de la carpeta, y navega
 * al canvas. Retorna los IDs de studio, folder y board.
 */
export async function setupStudioFolderAndBoard(page: Page) {
  await page.goto("/");
  // Manejar tanto el estado vacío como el que ya tiene Studios
  const emptyBtn = page.getByTestId("empty-create-studio");
  const createBtn = page.getByTestId("create-studio-card");
  await expect(emptyBtn.or(createBtn).first()).toBeVisible({ timeout: 10_000 });
  const createCardVisible = await createBtn.isVisible().catch(() => false);
  if (createCardVisible) {
    await createBtn.click();
  } else {
    await emptyBtn.click();
  }
  await expect(page.getByTestId("create-studio-modal")).toBeVisible();
  await page.getByTestId("studio-name-input").fill("F Studio");
  await page.getByTestId("studio-create-btn").click();
  await expect(page.getByTestId("create-studio-modal")).not.toBeVisible();
  await expect(page.getByTestId(/^studio-card-/).first()).toBeVisible({ timeout: 5_000 });
  const studioCard = page.getByTestId(/^studio-card-/).first();
  const studioId = (await studioCard.getAttribute("data-testid"))!.replace("studio-card-", "");
  await studioCard.click();

  // Studio view — crear carpeta
  await expect(page.getByTestId("create-folder-card")).toBeVisible({ timeout: 5_000 });
  await page.getByTestId("create-folder-card").click();
  await expect(page.getByTestId("create-folder-modal")).toBeVisible();
  await page.getByTestId("folder-name-input").fill("Test Folder");
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes("/api/folders") && r.request().method() === "POST",
      { timeout: 10_000 },
    ),
    page.getByTestId("folder-create-btn").click(),
  ]);
  await expect(page.getByTestId("create-folder-modal")).not.toBeVisible({ timeout: 5_000 });

  // Entrar en la carpeta
  await expect(page.getByTestId(/^folder-card-/).first()).toBeVisible({ timeout: 5_000 });
  const folderCard = page.getByTestId(/^folder-card-/).first();
  const folderId = (await folderCard.getAttribute("data-testid"))!.replace("folder-card-", "");
  await folderCard.click();

  // Folder view — crear board
  await expect(page.getByTestId("create-board-btn")).toBeVisible({ timeout: 5_000 });
  await page.getByTestId("create-board-btn").click();
  await waitForBoardLoaded(page);

  return { studioId, folderId };
}
