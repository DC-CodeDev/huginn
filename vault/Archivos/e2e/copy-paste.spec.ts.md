**Ruta:** `e2e/copy-paste.spec.ts`

## Responsabilidad
Test e2e de Playwright que valida el flujo completo de copiar y pegar un nodo con Ctrl+C / Ctrl+V.

## Exporta
- (ninguna — spec de Playwright)

## Casos cubiertos

### `"Ctrl+C + Ctrl+V crea nodo con mismo contenido, sin edges nuevas, en posición offset; segundo paste acumula offset"`
1. Crea un nodo card y le da el título `"CopyPasteTest"`.
2. Selecciona el nodo haciendo click en `span.rounded-full` (dot del encabezado, no un input) para que el handler de teclado no haga early-return.
3. Espera que la barra de acciones (`"Eliminar"`) sea visible — confirma que React tiene `selection` activo.
4. Presiona Ctrl+C.
5. **Primer paste** (Ctrl+V): verifica que aparece un nodo nuevo, que tiene el mismo título, que no hay aristas nuevas, y que su posición es `(origX+20, origY+20)`. Usa `data-node-x`/`data-node-y` expuestos por [[../../../Archivos/src/components/NodeCard.tsx.md]] y `data-testid="canvas-edges"` expuesto por [[../../../Archivos/src/NodeBoard.tsx.md]] para el SVG.
6. **Segundo paste** (Ctrl+V sin re-copiar): verifica que el offset se acumula sobre el primer pegado, no sobre el original — posición `(p1X+20, p1Y+20)`.

### `"Ctrl+C con multiples nodos seleccionados preserva posiciones relativas y no crea edges entre copias"`
1. Crea dos nodos, los separa con `dragNodeBy`.
2. Selecciona ambos con click + shift+click.
3. Ctrl+C + Ctrl+V → verifica que aparecen exactamente 2 nodos nuevos.
4. Verifica que no se crean edges nuevas (incluyendo entre las propias copias).
5. Verifica que los dos nodos pegados quedan seleccionados (barra visible).
6. Verifica que cada copia está en `(originalX+20, originalY+20)`.
7. Verifica que la distancia relativa entre las copias = distancia entre los originales (`px2-px1 ≈ x2-x1`, `py2-py1 ≈ y2-y1`).

## Notas de implementación
- `findNewIds(before, after)` — función local que devuelve los testids presentes en `after` pero no en `before`; robusto frente al estado acumulado de la DB de test.
- El SVG de aristas usa `[data-testid='canvas-edges'] path:not([stroke='transparent'])` para excluir los paths de íconos Lucide que comparten el mismo árbol SVG de la toolbar.
- El click en `span.rounded-full` (en lugar del div del nodo) es el mecanismo correcto para seleccionar sin dar foco a ningún input: `onStartDrag` → `setSelection`, sin que `document.activeElement` sea un INPUT.
- `newIds[0]` corresponde a la copia del nodo id1 y `newIds[1]` a id2 porque `clipboard` filtra `nodes` en su orden de inserción.

## Importa
- [[../../../Archivos/e2e/helpers.ts.md]] — `createCardNodeAndGetId`, `waitForBoardLoaded`, `dragNodeBy`
- Librerías externas: `@playwright/test`

## Importado por
- (ninguno — es un spec, no un helper)
