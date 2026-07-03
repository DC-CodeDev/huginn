**Ruta:** `e2e/helpers.ts`

## Responsabilidad
Helpers compartidos por los specs de Playwright, robustos frente al estado acumulado de la DB de test (verifican deltas, no conteos absolutos).

## Exporta
- `connectPorts(page, fromTestId, toTestId)` — conecta dos puertos con el mecanismo real: click en origen + click en destino (el handler es `onClick`, no drag)
- `waitForBoardLoaded(page)` — espera que `save-status` diga `"guardado"` (fin de la carga inicial), timeout 15 s
- `createCardNodeAndGetId(page)` — clickea `add-node-card` y devuelve el `data-testid` del nodo nuevo por diferencia contra los previos

## Importa
- Librerías externas: `@playwright/test` (`expect`, tipo `Page`)

## Importado por
- [[../../Archivos/e2e/create-node.spec.ts.md]] — `waitForBoardLoaded`
- [[../../Archivos/e2e/connect-edge.spec.ts.md]] — `connectPorts`, `createCardNodeAndGetId`, `waitForBoardLoaded`
- [[../../Archivos/e2e/persist.spec.ts.md]] — `waitForBoardLoaded`
