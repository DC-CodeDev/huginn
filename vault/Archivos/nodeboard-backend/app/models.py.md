**Ruta:** `nodeboard-backend/app/models.py`

## Responsabilidad
Modelos ORM (SQLAlchemy 2.x, estilo `Mapped`/`mapped_column`) — fuente de verdad de la forma persistida en `nodeboard.db`. Los nodos guardan sus partes flexibles como JSON; las aristas se guardan normalizadas (columnas planas).

## Exporta
- `Board` (tabla `boards`) — `id`, `name`, `created_at`, `updated_at`; relaciones `nodes` y `edges` con `cascade="all, delete-orphan"`
- `Node` (tabla `nodes`) — `id`, `board_id` (FK a boards, `ondelete=CASCADE`), `type` (`card`|`timeline`), `x`, `y`, `w`, `title`, y columnas JSON `ports`, `blocks`, `stages`, **`tags`** (default lista vacía)
- `Edge` (tabla `edges`) — `id`, `board_id` (FK), `from_node`, `from_port`, `to_node`, `to_port`, `curved` (bool), **`label`** (`String(300)`, default `""`)
- `_uuid()` — genera hex de UUID4 (default de PKs)
- `_now()` — `datetime` UTC aware (default/`onupdate` de timestamps); reutilizado por `main.py` como `models._now()`

## Notas de Fase 1
- **`Node.tags`**: `mapped_column(JSON, default=list)`, mismo patrón que `ports`/`blocks`/`stages`. Lista libre de strings, sin taxonomía cerrada (decisión 2.3 de la guía Fase 1).
- **`Edge.label`**: texto plano `String(300)` (no JSON), default `""`. Texto libre para explicar la conexión ("depende de", "contradice"…). Largo espejado de `title`.
- El esquema NO usa Alembic: `main.py` crea tablas con `Base.metadata.create_all()`, que **no altera** tablas existentes. Reflejar cambios de columna en la DB de dev exige `ALTER TABLE` manual (así se migró `nodeboard.db` en Paso 1, con backup previo y sin pérdida de datos).

## Importa
- [[../../../Archivos/nodeboard-backend/app/database.py.md]] — `Base`
- Librerías externas: `sqlalchemy` (`JSON`, `Boolean`, `DateTime`, `Float`, `ForeignKey`, `String`, `Mapped`, `mapped_column`, `relationship`), `uuid`, `datetime`

## Importado por
- [[../../../Archivos/nodeboard-backend/app/main.py.md]] — `models.Board`, `models.Node`, `models.Edge`, `models._now`
