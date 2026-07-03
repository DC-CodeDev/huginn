**Ruta:** `src/lib/canvas-types.ts`

## Responsabilidad
Tipos de apoyo del estado de interacción del canvas — no son dominio (eso es `types.ts`), sino estado efímero de la UI.

## Exporta
- `PortPos` — `{x, y, side, color}` (resultado de `portPos`)
- `Pending` — conexión en curso `{nodeId, portId, color}` | `null`
- `Selection` — `{type: "node"|"edge", id}` | `null`
- `ColorMenu` — `{nodeId, portId, x, y}` | `null` (menú de color en coords de pantalla)
- `DragState` — `{kind: "pan", …}` | `{kind: "node", id, ox, oy}` | `null`

## Importa
- [[../../../Archivos/src/types.ts.md]] — `PortColor`, `PortSide`

## Importado por
- [[../../../Archivos/src/NodeBoard.tsx.md]] — `Pending`, `DragState`, `Selection`, `ColorMenu`
- [[../../../Archivos/src/lib/geometry.ts.md]] — `PortPos`
- [[../../../Archivos/src/components/NodeCard.tsx.md]] — `Pending`
