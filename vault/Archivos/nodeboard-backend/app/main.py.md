**Ruta:** `nodeboard-backend/app/main.py`

## Responsabilidad
API REST del nodeboard — hub del backend. Define todos los endpoints, la creación de tablas al arrancar, CORS, el enforcement de foreign keys en SQLite, y la traducción entre el modelo plano de `Edge` y el shape anidado `from`/`to` que expone la API.

## Exporta
- `app` (instancia `FastAPI`, `lifespan`) — invocada por uvicorn como `app.main:app`
- `health()` — handler `GET /api/health` → `{"status": "ok"}` (importado por los tests)

## Comportamiento
1. `@event.listens_for(Engine, "connect")` → `PRAGMA foreign_keys=ON` (SQLite no aplica `ON DELETE CASCADE` sin esto)
2. `lifespan` → `Base.metadata.create_all(bind=engine)` al arrancar (crea tablas faltantes; **no** altera existentes)
3. CORS abierto a `localhost:5174`/`127.0.0.1:5174`/`localhost:3000`
4. Helpers: `_get_board`, `_node_to_schema` (`model_validate`, ya propaga `tags`), `_edge_to_schema` (traduce columnas planas ↔ `PortRef` anidado, incluye `label`), `_board_state`

### Endpoints
- Boards: `GET/POST /api/boards`, `GET/PATCH/DELETE /api/boards/{id}`, `PUT /api/boards/{id}/state` (autosave: borra y recrea nodos+aristas de forma atómica; propaga `tags` y `label`)
- Nodos: `POST /api/boards/{id}/nodes` (guarda `tags`), `PATCH /api/nodes/{id}` (parcial), `DELETE /api/nodes/{id}` (borra también sus aristas)
- Aristas: `POST /api/boards/{id}/edges` (guarda `label`; valida que los nodos existan, 422 si no), `PATCH /api/edges/{id}` (`curved` + `label`), `DELETE /api/edges/{id}`

## Propagación de `tags` / `label` (Fase 1 Paso 3 — hecho)
Se completó la propagación DB ↔ API de los campos nuevos:
- `_edge_to_schema` → agrega `label=e.label` en la lectura.
- `create_edge` → guarda `label=payload.label` (default `""` si ausente).
- `create_node` → guarda `tags=payload.tags` (default `[]` si ausente).
- `save_board_state` → propaga `tags` (nodos) y `label` (aristas) en el reemplazo total.
- `update_node` → el loop genérico `model_dump(exclude_unset=True)` ya distingue **ausente** (no pisa) de **presente**. Caso borde resuelto: `tags: null` explícito se coacciona a `[]` (limpiar), porque `NodeSchema.tags` es `list[str]` no-nullable y guardar `None` rompería la lectura (`ValidationError` en `_node_to_schema`).
- `update_edge` → aplica `label` con el mismo criterio `exclude_unset` que `update_node`/`tags`: **ausente** no toca, **presente** actualiza, `label: null` explícito → `""` (`EdgeSchema.label` es `str` no-nullable). **`curved` se dejó intacto a propósito**: usa el patrón previo `if payload.curved is not None` (ausente y null preservan). La inconsistencia es deliberada y está justificada por tipo: `label` es `str` (tiene vacío natural `""`), `curved` es `bool` (sin vacío natural, coaccionar `null` a un default sería artificial). Decisión confirmada con el usuario.

## Bug de serialización JSON en el borde schema→ORM (Paso 4 — fix)
**Causa:** desde Fase 1 Paso 2, `NodeSchema.ports/blocks/stages` son `list[Port]`/`list[Block]`/`list[TimelineStage]` (modelos Pydantic reales, no `dict[str, Any]`). `save_board_state` y `create_node` asignaban esos campos **directo** al `models.Node`, pero las columnas `JSON` de SQLAlchemy serializan con `json.dumps`, que no sabe convertir instancias Pydantic → al `db.commit()` explotaba con `TypeError: Object of type Port is not JSON serializable`. No apareció antes porque los tests solo usaban `ports/blocks/stages` vacíos (`[]` serializa bien).

**Fix:** aplanar con `model_dump()` (Pydantic 2.13.x lo hace recursivamente → dict/list JSON-safe) antes de asignar. Aplicado en:
- `save_board_state` → `dumped = n.model_dump()`; usa `dumped["ports"/"blocks"/"stages"/"tags"]`.
- `create_node` → idéntico con `payload.model_dump()`.
- `update_node` → **ya era correcto**, no se tocó: su loop usa `payload.model_dump(exclude_unset=True)`, que ya entrega estructuras planas.

`tags` (`list[str]`) nunca fue parte del bug (strings planos), pero se toma del mismo `dumped` por consistencia. Regresión cubierta por `test_save_board_state_with_real_ports_and_blocks_persists` y `test_create_node_with_real_ports_persists` en [[../tests/test_tags_label.py.md]].

## Importa
- [[../../../Archivos/nodeboard-backend/app/models.py.md]] — `models.Board`, `models.Node`, `models.Edge`, `models._now`
- [[../../../Archivos/nodeboard-backend/app/schemas.py.md]] — todos los schemas
- [[../../../Archivos/nodeboard-backend/app/database.py.md]] — `Base`, `engine`, `get_db`
- Librerías externas: `fastapi`, `sqlalchemy`, `uuid`, `contextlib`

## Importado por
- [[../../../Archivos/nodeboard-backend/tests/test_api.py.md]] — `app`, `health`
- [[../../../Archivos/nodeboard-backend/tests/test_tags_label.py.md]] — `app`, `get_db` (override) — tests e2e de `tags`/`label`
- Proceso uvicorn (entrypoint del backend)
