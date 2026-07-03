**Ruta:** `e2e/connect-edge.spec.ts`

## Responsabilidad
Test e2e: conectar `A.out` con `B.in` agrega una arista visible.

## Flujo del test
1. Crea dos nodos card (`createCardNodeAndGetId`); el segundo queda apilado sobre el primero
2. Arrastra B desde el borde del encabezado (zona de drag, no un input) para separarlos
3. Ubica los dots por orden de `node.ports`: `[0]="in"` (left), `[1]="out"` (right)
4. `connectPorts(A.out, B.in)` y verifica `edges === before + 1`
- Las aristas no tienen `data-testid`: se detectan como `<g>` dentro del `<svg width="1">` de conexiones

## Importa
- [[../../Archivos/e2e/helpers.ts.md]] — `connectPorts`, `createCardNodeAndGetId`, `waitForBoardLoaded`
- Librerías externas: `@playwright/test`

## Importado por
- (ninguno) — spec ejecutado por Playwright
