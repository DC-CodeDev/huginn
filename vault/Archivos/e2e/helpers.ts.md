**Ruta:** `e2e/helpers.ts`

## Responsabilidad
Helpers compartidos por los specs de Playwright, robustos frente al estado acumulado de la DB de test (verifican deltas, no conteos absolutos).

## Exporta
- `connectPorts(page, fromTestId, toTestId)` — conecta dos puertos con el mecanismo real: click en origen + click en destino (el handler es `onClick`, no drag)
- `waitForBoardLoaded(page)` — espera que `save-status` diga `"guardado"` (fin de la carga inicial), timeout 15 s
- `openTagsModal(page, nodeTestId)` — despliega el menú del nodo (`menu-{id}`) y clickea "Tags"; espera que el input del modal sea visible. Usa `data-testid="menu-{id}"` (no `node-menu-{id}`) para no colisionar con el selector `[data-testid^="node-"]`
- `dragNodeBy(page, nodeTestId, dx, dy)` — arrastra un nodo por su encabezado (zona sin campos) usando `mouse.move/down/up` con steps para separar nodos apilados
- `createCardNodeAndGetId(page)` — clickea `add-node-card` y devuelve el `data-testid` del nodo nuevo por diferencia contra los previos

## Importa
- Librerías externas: `@playwright/test` (`expect`, tipo `Page`)

## Importado por
- [[../../Archivos/e2e/create-node.spec.ts.md]] — `waitForBoardLoaded`
- [[../../Archivos/e2e/connect-edge.spec.ts.md]] — `connectPorts`, `createCardNodeAndGetId`, `waitForBoardLoaded`
- [[../../Archivos/e2e/persist.spec.ts.md]] — `waitForBoardLoaded`
- [[../../Archivos/e2e/copy-paste.spec.ts.md]] — `createCardNodeAndGetId`, `waitForBoardLoaded`
