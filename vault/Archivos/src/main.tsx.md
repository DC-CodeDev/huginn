**Ruta:** `src/main.tsx`

## Responsabilidad
Entrypoint del frontend. Monta la app React en `#root` dentro de `StrictMode` y carga los estilos globales.

## Exporta
- (nada) — módulo de arranque; efecto secundario: `createRoot(...).render(<NodeBoard />)`

## Importa
- [[../../Archivos/src/NodeBoard.tsx.md]] — `NodeBoard`
- [[../../Archivos/src/styles.css.md]] — estilos globales (import de efecto)
- Librerías externas: `react` (`StrictMode`), `react-dom/client` (`createRoot`)

## Importado por
- [[../../Archivos/index.html.md]] — cargado como `<script type="module" src="/src/main.tsx">`
