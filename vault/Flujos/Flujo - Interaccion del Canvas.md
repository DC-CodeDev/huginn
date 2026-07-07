## Flujo: Interacción del Canvas

> **Estado:** IMPLEMENTADO

Navegación y manipulación espacial del lienzo: zoom, pan, drag de nodos (individual y de grupo), selección y borrado. Todo vive en [[../Archivos/src/NodeBoard.tsx.md]].

### Vista (zoom / pan)
- `view = {x, y, z}`; `toWorld(sx, sy)` convierte pantalla → mundo.
- **Zoom**: listener `wheel` nativo no pasivo (`preventDefault`), zoom hacia el cursor, clamp `[0.25, 2.5]`. También botones ± y "restablecer vista" en la toolbar.
- **Pan**: `mousedown` sobre el fondo del lienzo setea `dragRef = {kind:"pan", ...}`; el `mousemove` global desplaza `view`.

### Drag de nodo individual
- `onStartDrag` en [[../Archivos/src/components/NodeCard.tsx.md]] setea `dragRef = {kind:"node", id, ox, oy}` (offset en coords de mundo). El `mousemove` global actualiza `x`/`y` del nodo como `w.x - ox`, sin acumular deltas frame a frame. `stopIfField` evita arrastrar cuando el mousedown cae sobre un campo de formulario.
- Este path se usa cuando: el nodo arrastrado no forma parte de una multi-selección, o el evento tiene shift/ctrl/meta (modificadores de selección).

### Drag de grupo (multi-selección)
- Activado cuando `!e.shiftKey && !e.ctrlKey && !e.metaKey && selectedNodeIds.length > 1 && selectedNodeIds.includes(node.id)`.
- Al iniciar el arrastre se captura:
  - `origins`: posición original de TODOS los nodos seleccionados en ese instante (`{ [id]: {x, y} }`).
  - `wx/wy`: posición inicial del mouse en coordenadas mundo.
  - `clickedId`: id del nodo que inició el drag.
- En cada `mousemove`: `delta = currentWorld - initialWorld`; cada nodo seleccionado se posiciona en `origins[id] + delta`. **Sin acumulación frame a frame** → no hay deriva por redondeo.
- La persistencia de posiciones finales ocurre automáticamente vía el debounce de `useBoardPersistence`.
- **Click sin arrastrar**: `groupDragMovedRef` permanece en `false` (el `mousemove` lo pone en `true`). En `mouseup`, si sigue en `false`, se llama `setSelectedNodeIds([clickedId])` — el plain click reemplaza la selección al nodo clickeado (comportamiento consistente con click simple). Esto distingue "empecé a arrastrar el grupo" de "hice click sobre un nodo del grupo".

### Selección y borrado
- Clic en nodo: `handleNodeClick` — si shift/ctrl alterna en `selectedNodeIds[]`; si no, reemplaza toda la selección por `[id]`; siempre limpia `selectedEdgeId`.
- Clic en arista: `selectedEdgeId = arista.id`, `selectedNodeIds = []`.
- Barra de acciones inferior: botón "Eliminar" (borra selección), toggle curvo/recto (solo si arista seleccionada).
- Teclado: `Delete`/`Backspace` borra la selección (ignora inputs); `Escape` cancela menús, `pending` y selección.
- `deleteSelection`: si hay nodos, los elimina todos y filtra sus aristas; si hay arista, la elimina.

### Puertos y color
- Doble clic en un dot cicla su color (`cyclePortColor`); clic derecho abre el menú de colores (`ColorMenu`) con `PORT_COLORS`.

## Notas
- El estado efímero de interacción está tipado en [[../Archivos/src/lib/canvas-types.ts.md]] (`DragState` con variantes `pan`/`node`/`group`, `Pending`, `ColorMenu`).
- El tema visual (dark/light) sale de [[../Archivos/src/lib/theme.ts.md]] y se pasa como `T` a todos los componentes.
- Tests de drag de grupo y selección: [[../Archivos/e2e/multi-select.spec.ts.md]].
