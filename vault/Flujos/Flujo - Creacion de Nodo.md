## Flujo: Creación de Nodo

> **Estado:** IMPLEMENTADO

Desde el disparo del usuario hasta que el nodo queda persistido.

Secuencia:

1. [[../Archivos/src/NodeBoard.tsx.md]] — disparadores: botón `add-node-card` / `add-node-timeline` de la toolbar ([[../Archivos/src/components/ToolBtn.tsx.md]]), o **doble clic en el lienzo** (crea un card en la posición del cursor vía `toWorld`).
2. `addNode(type, at?)` arma el nodo base con `uid()` ([[../Archivos/src/lib/id.ts.md]]): un card trae 2 puertos (`in`/`out`) y un bloque de texto vacío; un timeline trae una etapa inicial y sin puertos. Se agrega al estado `nodes`.
3. [[../Archivos/src/components/NodeCard.tsx.md]] — el nuevo nodo se renderiza; el usuario puede editar título, puertos, bloques o etapas.
4. El cambio de `nodes` dispara el **autosave** → ver [[Flujo - Carga y Autosave del Tablero.md]] (PUT `/state`), que persiste el nodo en `nodeboard.db`.

## Notas
- El id del frontend (`uid()`) es provisional; el backend puede asignar su propio `id` (`_uuid`) al persistir.
- También existe el endpoint granular `POST /api/boards/{id}/nodes` ([[../Archivos/nodeboard-backend/app/main.py.md]]), pero el frontend hoy usa el autosave de estado completo, no la creación granular.
- Cubierto por el e2e [[../Archivos/e2e/create-node.spec.ts.md]].
