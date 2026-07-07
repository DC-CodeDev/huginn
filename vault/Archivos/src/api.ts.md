**Ruta:** `src/api.ts`

## Responsabilidad
Capa HTTP hacia el backend y hook de persistencia del tablero. Encapsula fetch + manejo de errores y el ciclo de carga inicial + autosave con debounce.

## Exporta
- `SaveStatus` — `"cargando" | "guardando" | "guardado" | "error"`, usado por el contexto PWA para gobernar actualizaciones
- `api` — objeto con `listBoards`, `createBoard(name)`, `getBoard(id)`, `saveState(id, {nodes, edges})`; todos via `request<T>` sobre `BASE = VITE_API_URL ?? ""`
- `useBoardPersistence({nodes, edges, setNodes, setEdges, debounceMs=800})` — hook que:
  1. Al montar: lista boards; abre el primero o crea uno; setea `nodes`/`edges`/`boardId`; marca `loadedRef`. Usa `AbortController` para cancelar en unmount.
  2. Cada cambio en `nodes`/`edges` programa un autosave diferido (`setTimeout` + ref de cancelacion).
  3. Guarda estado completo via `PUT /api/boards/{id}/state`.
  4. Expone `status: SaveStatus`, `error: string | null`, `boardId`.
- `apiFetch(url, options)` — fetch centralizado con `credentials: "include"`, util para auth.

## Importa
- Librerias externas: `react` (`useState`, `useEffect`, `useRef`, `useCallback`)
- Internos: `./types` (`Node`, `Edge`)

## Importado por
- [[./NodeBoard.tsx.md]]
- [[./lib/auth-context.tsx.md]]
- [[../components/Home.tsx.md]]
- [[../components/FolderView.tsx.md]]
- [[../components/StudioView.tsx.md]]
