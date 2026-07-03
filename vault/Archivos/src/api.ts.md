**Ruta:** `src/api.ts`

## Responsabilidad
Capa HTTP hacia el backend y hook de persistencia del tablero. Encapsula fetch + manejo de errores y el ciclo de carga inicial + autosave con debounce.

## Exporta
- `SaveStatus` — `"cargando" | "guardando" | "guardado" | "error"`
- `api` — objeto con `listBoards`, `createBoard(name)`, `getBoard(id)`, `saveState(id, {nodes, edges})`; todos vía `request<T>` sobre `BASE = VITE_API_URL ?? ""`
- `useBoardPersistence({nodes, edges, setNodes, setEdges, debounceMs=800})` — hook que:
  1. Al montar: lista boards; abre el primero o crea uno; setea `nodes`/`edges`/`boardId`; marca `loadedRef`. Usa `AbortController` para cancelar en unmount.
  2. Ante cambios de `nodes`/`edges` (post-carga): `setTimeout` con debounce → `api.saveState`; actualiza `status`.
  - Retorna `{boardId, status}`.

## Comportamiento clave
- `request<T>` agrega header JSON, lanza `Error` con status+body si `!ok`, y devuelve `null` para 204.
- El autosave no dispara hasta que `loadedRef.current` es true (evita pisar la DB con el estado inicial antes de cargar).

## Importa
- [[../../Archivos/src/types.ts.md]] — `Node`, `Edge`
- Librerías externas: `react` (`useEffect`, `useRef`, `useState`, tipos `Dispatch`/`SetStateAction`)

## Importado por
- [[../../Archivos/src/NodeBoard.tsx.md]] — `useBoardPersistence`
