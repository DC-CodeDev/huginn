**Ruta:** `nodeboard-backend/tests/test_tags_label.py`

## Responsabilidad
Tests del contrato DB ↔ API de `Node.tags` y `Edge.label` — Fase 1 Paso 3 — más la regresión de serialización JSON del Paso 4. Anclan que futuros cambios en `main.py` no vuelvan a dropear estos campos silenciosamente (el bug original no rompía ningún test previo).

## Fixture
- `db` — sesión aislada contra una SQLite **en memoria** (`sqlite:///:memory:`). Los tests llaman las funciones de ruta de `main.py` **directamente** (no vía `TestClient`), para evitar el bootstrap ASGI/lifespan del backend, que en este entorno queda bloqueado, sin perder la semántica real de persistencia.
- Helpers: `_board(db)`, `_make_node(id, **overrides)`, `_board_with_edge(db, label, curved)`, `_node_with_ports(id)`.

## Exporta (casos de test)
- `test_create_node_tags_roundtrip` — POST nodo con `tags` → vuelve en el POST y en el GET del board
- `test_create_node_without_tags_defaults_empty` — nodo sin `tags` → `[]`
- `test_create_edge_label_roundtrip` — POST arista con `label` → vuelve en POST y GET
- `test_create_edge_without_label_defaults_empty` — arista sin `label` → `""`
- `test_save_board_state_propagates_tags_and_label` — `PUT /state` preserva `tags` y `label` en el reemplazo total
- `test_update_node_tags_absent_preserves` — PATCH sin la clave `tags` no pisa el valor existente
- `test_update_node_tags_present_updates` — PATCH con `tags` lo actualiza
- `test_update_node_tags_null_clears` — `tags: null` explícito limpia a `[]` (distinto de ausente; no 500)
- `test_update_edge_label_absent_preserves` — PATCH sin `label` no lo pisa (y `curved` cambia OK)
- `test_update_edge_label_present_updates` — PATCH solo `label` actualiza y persiste vía GET, sin afectar `curved`
- `test_update_edge_label_null_clears` — `label: null` explícito vacía a `""` (mismo criterio que `tags`; no 500)
- `test_save_board_state_with_real_ports_and_blocks_persists` — **regresión Paso 4**: `save_board_state` con `ports`/`blocks` reales (modelos Pydantic) persiste sin `TypeError` y se relee
- `test_create_node_with_real_ports_persists` — **regresión Paso 4**: `create_node` con `ports` reales persiste sin `TypeError`

## Importa
- [[../app/main.py.md]] — funciones de ruta (`create_board`, `create_node`, `create_edge`, `update_node`, `update_edge`, `save_board_state`, `get_board`)
- [[../app/database.py.md]] — `Base`
- [[../app/schemas.py.md]] — `BoardCreate`, `BoardStateSave`, `NodeSchema`, `NodeUpdate`, `EdgeSchema`, `EdgeUpdate`, `Port`, `PortRef`
- Librerías: `pytest`, `sqlalchemy`

## Importado por
- (ninguno) — suite de tests
