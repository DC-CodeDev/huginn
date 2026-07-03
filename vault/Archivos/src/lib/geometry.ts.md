**Ruta:** `src/lib/geometry.ts`

## Responsabilidad
Utilidades de geometría puras del canvas: posición en pantalla de un puerto y path SVG de una arista. Sin estado ni React — testeable de forma aislada.

## Exporta
- `PORT_Y0 = 56` — y del primer puerto relativo al nodo
- `PORT_DY = 26` — separación vertical entre puertos del mismo lado
- `portPos(node, portId): PortPos | null` — calcula `{x, y, side, color}`; la `y` se indexa por posición **dentro del mismo lado** (`samesSide`), no en el array global; `x` = `node.x` (left) o `node.x + node.w` (right); `null` si el puerto no existe
- `edgePath(a, b, curved): string` — path SVG; recto (`M … L …`) si `!curved`, o curva Bézier cúbica con `dx = max(60, |b.x-a.x|/2)` y puntos de control según el `side` de cada extremo

## Importa
- [[../../../Archivos/src/types.ts.md]] — `Node`, `PortSide`
- [[../../../Archivos/src/lib/canvas-types.ts.md]] — `PortPos`

## Importado por
- [[../../../Archivos/src/NodeBoard.tsx.md]] — `portPos`, `edgePath` (render de aristas)
- [[../../../Archivos/src/components/NodeCard.tsx.md]] — `PORT_Y0`, `PORT_DY` (posición de dots y labels)
- [[../../../Archivos/src/lib/geometry.test.ts.md]] — todo (bajo test)
