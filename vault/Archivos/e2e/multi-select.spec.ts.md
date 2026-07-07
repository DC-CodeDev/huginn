**Ruta:** `e2e/multi-select.spec.ts`

## Responsabilidad
Tests e2e (Playwright) de la multi-selección de nodos con modificadores de teclado.

## Tests incluidos
- **shift+click agrega y quita nodos de la seleccion** — click simple en N1 → solo N1 seleccionado; shift+click en N2 → ambos; shift+click en N2 de nuevo → solo N1
- **ctrl+click agrega y quita nodos de la seleccion** — ídem con `Control` en lugar de `Shift`
- **click simple reemplaza toda la seleccion existente** — construye selección múltiple con shift; un click simple en N1 deja solo N1
- **click en canvas vacio deselecciona todo** — verifica que mousedown sobre el fondo limpia `selectedNodeIds` y oculta la barra de selección
- **arrastrar un nodo de una seleccion multiple mueve todo el grupo manteniendo distancias relativas** — crea dos nodos, los multi-selecciona, arrastra N1 por (50,60)px; verifica que ambos se movieron, que su delta fue el mismo, y que la distancia relativa entre ellos se preservó
- **arrastrar un nodo que NO esta en una seleccion multiple no mueve el resto** — N1 y N2 existen; solo N2 seleccionado (selección simple); arrastrar N1; verifica que N1 se movió y N2 no

## Técnica de verificación
Usa el atributo `data-selected` del div raíz del nodo (expuesto por [[../../../Archivos/src/components/NodeCard.tsx.md]]) para confirmar el estado de selección sin acceder al estado React.

## Importa helpers
- [[../../../Archivos/e2e/helpers.ts.md]] — `createCardNodeAndGetId`, `waitForBoardLoaded`, `dragNodeBy`
