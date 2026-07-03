**Ruta:** `src/lib/theme.ts`

## Responsabilidad
Tema visual del canvas: paletas dark/light y la interfaz que las tipa. Todos los componentes reciben el objeto `Theme` activo (`T`) por props y lo usan para colores inline.

## Exporta
- `Theme` (interface) — `{bg, dot, card, cardBorder, field, fieldBorder, text, sub}`
- `THEMES: Record<string, Theme>` — `dark` y `light`

## Importa
- (ninguno)

## Importado por
- [[../../../Archivos/src/NodeBoard.tsx.md]] — `THEMES`
- [[../../../Archivos/src/components/NodeCard.tsx.md]] — `Theme`
- [[../../../Archivos/src/components/Block.tsx.md]] — `Theme`
- [[../../../Archivos/src/components/Timeline.tsx.md]] — `Theme`
- [[../../../Archivos/src/components/MenuItem.tsx.md]] — `Theme`
- [[../../../Archivos/src/components/MiniBtn.tsx.md]] — `Theme`
- [[../../../Archivos/src/components/ToolBtn.tsx.md]] — `Theme`
- [[../../../Archivos/src/components/Sep.tsx.md]] — `Theme`
