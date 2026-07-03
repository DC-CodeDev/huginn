## Flujo: Interacción del Canvas

> **Estado:** IMPLEMENTADO

Navegación y manipulación espacial del lienzo: zoom, pan, drag de nodos, selección y borrado. Todo vive en [[../Archivos/src/NodeBoard.tsx.md]].

### Vista (zoom / pan)
- `view = {x, y, z}`; `toWorld(sx, sy)` convierte pantalla → mundo.
- **Zoom**: listener `wheel` nativo no pasivo (`preventDefault`), zoom hacia el cursor, clamp `[0.25, 2.5]`. También botones ± y "restablecer vista" en la toolbar.
- **Pan**: `mousedown` sobre el fondo del lienzo setea `dragRef = {kind:"pan", ...}`; el `mousemove` global desplaza `view`.

### Drag de nodos
- `onStartDrag` en [[../Archivos/src/components/NodeCard.tsx.md]] setea `dragRef = {kind:"node", id, ox, oy}` (offset en coords de mundo). El `mousemove` global actualiza `x`/`y` del nodo. `stopIfField` evita arrastrar cuando el mousedown cae sobre un campo de formulario.

### Selección y borrado
- Clic en nodo o arista → `selection = {type, id}`; barra de acciones inferior (borrar; en aristas, curvo/recto).
- Teclado: `Delete`/`Backspace` borra la selección (ignora inputs); `Escape` cancela menús, `pending` y selección.
- `deleteSelection`: si es nodo, lo quita y filtra sus aristas; si es arista, la quita.

### Puertos y color
- Doble clic en un dot cicla su color (`cyclePortColor`); clic derecho abre el menú de colores (`ColorMenu`) con `PORT_COLORS`.

## Notas
- El estado efímero de interacción está tipado en [[../Archivos/src/lib/canvas-types.ts.md]] (`DragState`, `Selection`, `Pending`, `ColorMenu`).
- El tema visual (dark/light) sale de [[../Archivos/src/lib/theme.ts.md]] y se pasa como `T` a todos los componentes.
