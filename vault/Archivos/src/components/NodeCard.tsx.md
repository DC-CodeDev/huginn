**Ruta:** `src/components/NodeCard.tsx`

## Responsabilidad
Componente más complejo del frontend: dibuja un nodo completo (card o timeline) y todos sus sub-elementos interactivos. Recibe callbacks desde `NodeBoard` y no gestiona estado global propio (salvo drafts locales de sub-componentes).

## Exporta
- `NodeCard(props)` — props: `node`, `T`, `theme`, `selected`, `onSelect`, `onStartDrag`, `onDelete`, `update`, `onPortClick`, `onPortCycle`, `onPortContext`, `pending`, `menuOpen`, `onOpenMenu`

## Comportamiento
- **Encabezado**: input de `title`, botón "+" (abre menú añadir), botón borrar. Handle de drag = zona sin campos de formulario (`stopIfField` detecta input/textarea/button/select/label)
- **Selección**: el componente NO conoce la lógica de multi-selección. `onMouseDown` en el cuerpo del card llama `onSelect(e)` (si el target es un campo) o `onStartDrag(e)`. Ambos pasan el `ReactMouseEvent` completo —con `shiftKey`/`ctrlKey`— hacia `NodeBoard` que decide qué hacer
- **Menú añadir** (`menuOpen`): para card → bloques texto/número/tabla/imagen; para timeline → "añadir etapa"; ambos → puerto de entrada/salida. Botón del menú: `data-testid="menu-{id}"` (prefijo `menu-`, no `node-`, para no colisionar con el selector `[data-testid^="node-"]` de los tests)
- **Puertos**: labels editables por lado (left/right) y dots de conexión posicionados con `PORT_Y0`/`PORT_DY`. Dot: click = conectar (`onPortClick`), doble click = ciclar color (`onPortCycle`), click derecho = menú de color (`onPortContext`)
- **Contenido**: card renderiza `Block` por cada bloque; timeline renderiza `Timeline`
- **Atributos del div raíz**: `data-node-x={node.x}`, `data-node-y={node.y}` (posición para tests) y `data-selected={selected}` (estado de selección para tests e2e)

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
