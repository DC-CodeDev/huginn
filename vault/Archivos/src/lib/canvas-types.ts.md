**Ruta:** `src/lib/canvas-types.ts`

## Responsabilidad
Tipos de apoyo del estado de interacción del canvas — no son dominio (eso es `types.ts`), sino estado efímero de la UI.

## Exporta
- `PortPos` — `{x, y, side, color}` (resultado de `portPos`)
- `Pending` — conexión en curso `{nodeId, portId, color}` | `null`
- `ColorMenu` — `{nodeId, portId, x, y}` | `null` (menú de color en coords de pantalla)
- `DragState` — `{kind: "pan", …}` | `{kind: "node", id, ox, oy}` | `{kind: "group", ids, origins, wx, wy, clickedId}` | `null`

> `Selection` fue eliminado en Fase 2 multi-selección. La selección de nodos es ahora `selectedNodeIds: string[]` y la de arista `selectedEdgeId: string | null`, ambos estados locales en `NodeBoard` sin tipo importado.

## Importa
- [[../../../Archivos/src/types.ts.md]] — `PortColor`, `PortSide`

## Importado por
- [[../../../Archivos/src/NodeBoard.tsx.md]] — `Pending`, `DragState`, `ColorMenu`
- [[../../../Archivos/src/lib/geometry.ts.md]] — `PortPos`
- [[../../../Archivos/src/components/NodeCard.tsx.md]] — `Pending`
