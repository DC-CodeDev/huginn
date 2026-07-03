**Ruta:** `src/components/Block.tsx`

## Responsabilidad
Renderiza y edita un bloque de un nodo card, con una variante por cada `type` del union `Block`. Cada bloque se envuelve con un botón de borrado que aparece en hover.

## Exporta
- `Block({block, T, update, remove})` — despacha por `block.type`:
  - `text` — textarea con auto-resize (ajusta `height` a `scrollHeight`)
  - `number` — input de valor grande + input de `label`
  - `table` — grilla editable con `MiniBtn` para +/− fila y +/− columna
  - `image` — preview clickeable o botón "subir imagen"; lee el archivo con `FileReader` a data URL (`src`)

## Importa
- [[../../../Archivos/src/types.ts.md]] — `Block` (como `BlockT`)
- [[../../../Archivos/src/lib/theme.ts.md]] — `Theme`
- [[../../../Archivos/src/components/MiniBtn.tsx.md]] — `MiniBtn`
- Librerías externas: `react`, `lucide-react`

## Importado por
- [[../../../Archivos/src/components/NodeCard.tsx.md]] — `Block`
