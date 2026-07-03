**Ruta:** `src/NodeBoard.tsx`

## Responsabilidad
Hub del frontend: componente raíz del canvas. Orquesta estado (nodos, aristas, selección, conexión en curso, vista), interacción (zoom/pan/drag, teclado), render de aristas SVG, toolbar y menús contextuales. Delega el dibujo de cada nodo a `NodeCard`.

## Exporta
- `default NodeBoard()` — componente React

## Estado y refs
- `nodes`/`edges` (con `initialNodes`/`initialEdges` de demo, reemplazados por la carga de `useBoardPersistence`). Desde Fase 1 Paso 4, la semilla y el factory `addNode` inicializan `tags: []` en cada nodo y `label: ""` en cada arista (campos requeridos en [[types.ts.md]]); sin UI para editarlos todavía — eso es Fase 2
- `theme`, `selection`, `pending` (conexión en curso), `mouseWorld`, `menuNode`, `colorMenu`, `defaultCurved`, `view` (`{x,y,z}`)
- `viewRef`/`dragRef`/`canvasRef` — refs para lógica no reactiva

## Comportamiento clave
- `toWorld(sx,sy)` — convierte coordenadas de pantalla a mundo según `view`
- Zoom: listener `wheel` nativo no pasivo (para poder `preventDefault`), zoom hacia el cursor, clamp `[0.25, 2.5]`
- Drag global (`mousemove`/`mouseup`): pan del lienzo o arrastre de nodo según `dragRef.current.kind`
- Teclado: `Delete`/`Backspace` borra la selección (ignora inputs/textarea); `Escape` cancela menús/pending/selección
- `addNode`, `deleteSelection`, `updateNode`, `onPortClick` (inicia/termina conexión), `cyclePortColor`
- Render: aristas como `<path>` (uno transparente ancho para el click, otro visible) dentro de `<svg width="1">`; `pending` como línea punteada al mouse
- UI: toolbar (añadir nodo/timeline, estado de guardado, curvo/recto, tema, zoom), barra de acciones de selección, menú de colores, ayuda

## Importa
- [[../../Archivos/src/api.ts.md]] — `useBoardPersistence`
- [[../../Archivos/src/types.ts.md]] — `PORT_COLORS`, `Node`, `Edge`, `Port`
- [[../../Archivos/src/lib/canvas-types.ts.md]] — `Pending`, `DragState`, `Selection`, `ColorMenu`
- [[../../Archivos/src/lib/geometry.ts.md]] — `portPos`, `edgePath`
- [[../../Archivos/src/lib/theme.ts.md]] — `THEMES`
- [[../../Archivos/src/lib/id.ts.md]] — `uid`
- [[../../Archivos/src/components/NodeCard.tsx.md]] — `NodeCard`
- [[../../Archivos/src/components/ToolBtn.tsx.md]] — `ToolBtn`
- [[../../Archivos/src/components/Sep.tsx.md]] — `Sep`
- Librerías externas: `react`, `lucide-react`

## Importado por
- [[../../Archivos/src/main.tsx.md]] — `NodeBoard`
