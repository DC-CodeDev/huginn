**Ruta:** `nodeboard-backend/app/database.py`

## Responsabilidad
Configuración de la base de datos (SQLite + SQLAlchemy 2.x): engine, factory de sesiones, `Base` declarativa y la dependencia de sesión por request de FastAPI.

## Exporta
- `DATABASE_URL` (const) — `sqlite:///./nodeboard.db` por default; sobreescribible con la env var `NODEBOARD_DB` (la usan `dev:api` y la config e2e para aislar DBs)
- `engine` — engine SQLite con `check_same_thread=False`
- `SessionLocal` — factory de sesiones (`autoflush=False`, `autocommit=False`)
- `Base` — `DeclarativeBase` del que heredan todos los modelos
- `get_db()` — dependencia FastAPI: yield de una sesión por request, cierre en `finally`

## Importa
- Librerías externas: `sqlalchemy` (`create_engine`), `sqlalchemy.orm` (`DeclarativeBase`, `sessionmaker`), `os`

## Importado por
- [[../../../Archivos/nodeboard-backend/app/models.py.md]] — `Base`
- [[../../../Archivos/nodeboard-backend/app/main.py.md]] — `engine`, `get_db`
- [[../../../Archivos/nodeboard-backend/migrations/env.py.md]] — `Base`
