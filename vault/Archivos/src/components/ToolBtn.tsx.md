**Ruta:** `src/components/ToolBtn.tsx`

## Responsabilidad
Botón de la barra de herramientas superior (icono con `title` y `data-testid` opcional para e2e).

## Exporta
- `ToolBtn({T, label, onClick, children, testId?})` — `label` va como `title`; `testId` como `data-testid` (ej. `add-node-card`, `add-node-timeline`, usados por los tests de Playwright)

## Importa
- [[../../../Archivos/src/lib/theme.ts.md]] — `Theme`
- Librerías externas: `react` (tipo `ReactNode`)

## Importado por
- [[../../../Archivos/src/NodeBoard.tsx.md]] — `ToolBtn`
