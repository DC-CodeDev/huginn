## Flujo: Carga y Autosave del Tablero

> **Estado:** IMPLEMENTADO (frontend + backend)

Cómo el canvas carga su estado al arrancar y lo persiste automáticamente ante cada cambio, sin botón de guardar.

Secuencia:

1. [[../Archivos/src/main.tsx.md]] — monta `<NodeBoard />`.
2. [[../Archivos/src/NodeBoard.tsx.md]] — llama `useBoardPersistence({nodes, edges, setNodes, setEdges})`; `status` alimenta el indicador `save-status` de la toolbar.
3. [[../Archivos/src/api.ts.md]] — **carga inicial**: `api.listBoards()`; si hay boards abre el primero con `api.getBoard(id)`, si no crea uno con `api.createBoard()`. Setea `nodes`/`edges`/`boardId`, marca `loadedRef` y pone `status="guardado"`. `AbortController` cancela si el componente se desmonta.
4. [[../Archivos/nodeboard-backend/app/main.py.md]] — `GET /api/boards` y `GET /api/boards/{id}` devuelven el estado; `_board_state` arma `BoardState` con nodos y aristas (traduciendo `Edge` plano ↔ anidado).
5. **Autosave**: ante cambios de `nodes`/`edges` (y solo si `loadedRef` es true), `api.ts` dispara un `setTimeout` con debounce de 800 ms → `api.saveState(boardId, {nodes, edges})` = `PUT /api/boards/{id}/state`.
6. [[../Archivos/nodeboard-backend/app/main.py.md]] — `save_board_state` reemplaza todo el estado de forma atómica: borra nodos y aristas existentes y recrea desde el payload; actualiza `updated_at`.
7. [[../Archivos/nodeboard-backend/app/models.py.md]] — la persistencia real ocurre sobre `nodeboard.db` (JSON para `ports`/`blocks`/`stages`/`tags`, columnas planas para `Edge`).

## Notas
- El indicador de estado transita `cargando → guardando → guardado` (o `error` si falla la conexión).
- El delta de una edición dispara un único PUT por ventana de debounce; ediciones rápidas se agrupan.
- El e2e [[../Archivos/e2e/persist.spec.ts.md]] valida este ciclo completo (crear → autosave → reload → sigue presente).
