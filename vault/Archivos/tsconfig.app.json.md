**Ruta:** `tsconfig.app.json`

## Responsabilidad
Config de TypeScript para el código de la app (`src`). Es la referencia principal del build tipado (`tsc -b`).

## Contenido clave
- `target`/`lib`: ES2022 + DOM
- `strict: true`, `noEmit: true`, `jsx: "react-jsx"`, `moduleResolution: "Bundler"`, `isolatedModules`, `resolveJsonModule`
- `include: ["src"]`

## Nota
El proyecto usa el patrón de tsconfigs de referencia: `tsconfig.json` (raíz, referencias), `tsconfig.app.json` (app) y `tsconfig.node.json` (config de build/tooling). Fase 0 dejó el frontend compilando en modo estricto sin `@ts-nocheck`.

## Importado por
- `tsc -b` (vía `tsconfig.json`) y el toolchain de Vite
