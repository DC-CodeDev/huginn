**Ruta:** `nodeboard-backend/migrations/versions/e10b08b208d0_initial_schema.py`

## Responsabilidad
Migración baseline generada con `alembic revision --autogenerate -m "initial_schema"`.
Representa el esquema completo de la base de datos tal cual existe en los modelos
(`studios`, `folders`, `boards`, `nodes`, `edges`). Es la primera revisión, sin
parent (`down_revision = None`).

## Contenido
### upgrade()
Crea las 5 tablas con sus columnas, tipos, claves foráneas e índices:

| Tabla | Columnas | FK |
|-------|----------|----|
| `studios` | `id` (String(32) PK), `name` (String(200)), `color` (String(20)) | — |
| `folders` | `id` (String(32) PK), `name` (String(200)), `studio_id` (String(32)) | `studio_id → studios.id ON DELETE CASCADE` |
| `boards` | `id` (String(32) PK), `name` (String(200)), `created_at` (DateTime(tz)), `updated_at` (DateTime(tz)), `studio_id` (String(32)), `folder_id` (String(32) nullable) | `studio_id → studios.id ON DELETE CASCADE`, `folder_id → folders.id ON DELETE SET NULL` |
| `edges` | `id` (String(64) PK), `board_id` (String(32)), `from_node` (String(64)), `from_port` (String(64)), `to_node` (String(64)), `to_port` (String(64)), `curved` (Boolean), `label` (String(300)) | `board_id → boards.id ON DELETE CASCADE` |
| `nodes` | `id` (String(64) PK), `board_id` (String(32)), `type` (String(20)), `x` (Float), `y` (Float), `w` (Float), `title` (String(300)), `ports` (JSON), `blocks` (JSON), `stages` (JSON), `tags` (JSON) | `board_id → boards.id ON DELETE CASCADE` |

### downgrade()
Elimina las tablas en orden inverso (respetando FKs): nodes → edges → boards → folders → studios.

## Validación
Se verificó que `alembic revision --autogenerate` sobre esta migración aplicada produce
un diff vacío (`upgrade(): pass`), confirmando que la baseline coincide exactamente con
los modelos actuales.

## Importado por
- `alembic upgrade head` (CLI o vía lifespan)
- [[../../../Archivos/nodeboard-backend/migrations/env.py.md]] — discovery automático de versiones en `migrations/versions/`
