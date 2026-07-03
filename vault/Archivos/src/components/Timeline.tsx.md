**Ruta:** `src/components/Timeline.tsx`

## Responsabilidad
Renderiza el contenido de un nodo `timeline`: una línea temporal con etapas alternadas izquierda/derecha, cada una con título editable y tags añadibles/removibles.

## Exporta
- `Timeline({node, T, update})` — `node` es `Extract<Node, {type: "timeline"}>`

## Comportamiento
- Estado local `tagDrafts` (`Record<stageId, string>`) para el input de nuevo tag por etapa
- `stageColor(i)` — color de la paleta (excluye el último de `PORT_COLORS`)
- Etapas alternan lado por índice par/impar, con hito central sobre línea punteada
- Tag: se agrega con Enter si el draft no está vacío; se quita con la "×" en hover
- Botones: "quitar etapa" (hover) y "+ Añadir etapa" al pie

## Importa
- [[../../../Archivos/src/types.ts.md]] — `Node`, `TimelineStage`, `PORT_COLORS`
- [[../../../Archivos/src/lib/theme.ts.md]] — `Theme`
- [[../../../Archivos/src/lib/id.ts.md]] — `uid`
- Librerías externas: `react`, `lucide-react`

## Importado por
- [[../../../Archivos/src/components/NodeCard.tsx.md]] — `Timeline`
