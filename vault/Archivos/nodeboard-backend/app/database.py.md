**Ruta:** `nodeboard-backend/app/database.py`

## Responsabilidad
Configuración de la base de datos (SQLite + SQLAlchemy 2.x): engine, factory de sesiones, `Base` declarativa y la dependencia de sesión por request de FastAPI.

## Exporta
- `get_database_url()` — función con precedencia: (1) `DATA_PATH` → ruta absoluta `sqlite:////{DATA_PATH}/nodeboard.db`, (2) `NODEBOARD_DB` (override legacy), (3) default `sqlite:///./nodeboard.db`
- `DATABASE_URL` (const) — resultado de `get_database_url()`
- `engine` — engine SQLite con `check_same_thread=False`
- `SessionLocal` — factory de sesiones (`autoflush=False`, `autocommit=False`)
- `Base` — `DeclarativeBase` del que heredan todos los modelos
- `get_db()` — dependencia FastAPI: yield de una sesión por request, cierre en `finally`

## Importa
- Librerías externas: `sqlalchemy` (`create_engine`), `sqlalchemy.orm` (`DeclarativeBase`, `sessionmaker`), `os`, `pathlib` (`Path`)

## Importado por
- [[../../../Archivos/nodeboard-backend/app/models.py.md]] — `Base`
- [[../../../Archivos/nodeboard-backend/app/main.py.md]] — `engine`, `get_db`
- [[../../../Archivos/nodeboard-backend/migrations/env.py.md]] — `Base`, `get_database_url`
