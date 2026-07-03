**Ruta:** `src/components/NodeCard.tsx`

## Responsabilidad
Componente más complejo del frontend: dibuja un nodo completo (card o timeline) y todos sus sub-elementos interactivos. Recibe callbacks desde `NodeBoard` y no gestiona estado global propio (salvo drafts locales de sub-componentes).

## Exporta
- `NodeCard(props)` — props: `node`, `T`, `theme`, `selected`, `onSelect`, `onStartDrag`, `onDelete`, `update`, `onPortClick`, `onPortCycle`, `onPortContext`, `pending`, `menuOpen`, `onOpenMenu`

## Comportamiento
- **Encabezado**: input de `title`, botón "+" (abre menú añadir), botón borrar. Handle de drag = zona sin campos de formulario (`stopIfField` detecta input/textarea/button/select/label)
- **Menú añadir** (`menuOpen`): para card → bloques texto/número/tabla/imagen; para timeline → "añadir etapa"; ambos → puerto de entrada/salida
- **Puertos**: labels editables por lado (left/right) y dots de conexión posicionados con `PORT_Y0`/`PORT_DY`. Dot: click = conectar (`onPortClick`), doble click = ciclar color (`onPortCycle`), click derecho = menú de color (`onPortContext`)
- **Contenido**: card renderiza `Block` por cada bloque; timeline renderiza `Timeline`

## Importa
- [[../../../Archivos/src/types.ts.md]] — `PORT_COLORS`, `Node`, `Port`
- [[../../../Archivos/src/lib/canvas-types.ts.md]] — `Pending`
- [[../../../Archivos/src/lib/geometry.ts.md]] — `PORT_Y0`, `PORT_DY`
- [[../../../Archivos/src/lib/theme.ts.md]] — `Theme`
- [[../../../Archivos/src/lib/id.ts.md]] — `uid`
- [[../../../Archivos/src/components/MenuItem.tsx.md]] — `MenuItem`
- [[../../../Archivos/src/components/Block.tsx.md]] — `Block`
- [[../../../Archivos/src/components/Timeline.tsx.md]] — `Timeline`
- Librerías externas: `react`, `lucide-react`

## Importado por
- [[../../../Archivos/src/NodeBoard.tsx.md]] — `NodeCard`
