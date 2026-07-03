**Ruta:** `src/types.ts`

## Responsabilidad
Fuente de verdad del dominio en el frontend. Define los tipos de nodo, arista, puerto y bloque, más la paleta de colores de puerto.

## Exporta
- `PORT_COLORS` (const tuple de 6 hex) y `PortColor` (union cerrado derivado) — paleta libre, decorativa (sin taxonomía impuesta)
- `PortSide` — `"left" | "right"`
- `Port` — `{id, side, color, label}`
- `Block` (union discriminado por `type`) — `text` `{value}` | `number` `{value, label}` | `table` `{data: string[][]}` | `image` `{src: string|null}`
- `TimelineStage` — `{id, title, tags: string[]}`
- `Node` (union discriminado por `type`) — `card` `{..., blocks: Block[]}` | `timeline` `{..., stages: TimelineStage[]}`; ambos comparten `id, x, y, w, title, ports, tags: string[]`
- `PortRef` — `{nodeId, portId}`
- `Edge` — `{id, from: PortRef, to: PortRef, curved, label: string}` (shape anidado; el plano `from_node`/… vive solo en la DB, traducido en `main.py`)

## `tags` / `label` en el frontend (Fase 1 Paso 4 — hecho)
- `Node` ahora incluye `tags: string[]` (requerido, inline en ambas ramas del union, mismo criterio que `ports`). `Edge` incluye `label: string` (requerido). Espejan `Node.tags` y `Edge.label` del backend.
- Son **requeridos** (no opcionales): el backend siempre los envía (default `[]` / `""`), así que al cargar están presentes. Los sitios de construcción local (semilla + factory en [[NodeBoard.tsx.md]], fixtures de [[../lib/geometry.test.ts.md]]) se completaron con `tags: []` / `label: ""`.
- **Todavía sin UI**: no hay editor de tags ni de label ni filtros — eso es Fase 2. Hoy viajan y persisten vacíos sin que el usuario pueda tocarlos.
- `api.ts` no necesitó cambios: transporta `Node[]`/`Edge[]` tal cual vía `JSON.stringify`, sin construir objetos parciales.

## Importa
- (ninguno) — módulo de tipos puro

## Importado por
- [[../../Archivos/src/NodeBoard.tsx.md]] — `Node`, `Edge`, `Port`, `PORT_COLORS`
- [[../../Archivos/src/api.ts.md]] — `Node`, `Edge`
- [[../../Archivos/src/lib/geometry.ts.md]] — `Node`, `PortSide`
- [[../../Archivos/src/lib/geometry.test.ts.md]] — `Node`, `Port`, `PORT_COLORS`
- [[../../Archivos/src/lib/canvas-types.ts.md]] — `PortColor`, `PortSide`
- [[../../Archivos/src/components/NodeCard.tsx.md]] — `Node`, `Port`, `PORT_COLORS`
- [[../../Archivos/src/components/Block.tsx.md]] — `Block`
- [[../../Archivos/src/components/Timeline.tsx.md]] — `Node`, `TimelineStage`, `PORT_COLORS`
