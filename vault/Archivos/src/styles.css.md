**Ruta:** `src/styles.css`

## Responsabilidad
Estilos globales: importa Tailwind y aplica un reset mínimo.

## Contenido
- `@import "tailwindcss";` — plugin Tailwind vía Vite
- `:root` — `font-synthesis: none`, `text-rendering: optimizeLegibility`
- Reset: `box-sizing: border-box`, `html/body/#root` a 100% sin margen, inputs/botones heredan la fuente

## Importa
- Tailwind (vía `@import`)

## Importado por
- [[../../Archivos/src/main.tsx.md]] — import de efecto
