**Ruta:** `e2e/create-node.spec.ts`

## Responsabilidad
Test e2e: crear un nodo card aumenta la cantidad de nodos en uno.

## Flujo del test
1. `goto("/")` + `waitForBoardLoaded`
2. cuenta nodos (`[data-testid^="node-"]`)
3. click en `add-node-card`
4. espera `count === before + 1`

## Importa
- [[../../Archivos/e2e/helpers.ts.md]] — `waitForBoardLoaded`
- Librerías externas: `@playwright/test`

## Importado por
- (ninguno) — spec ejecutado por Playwright
