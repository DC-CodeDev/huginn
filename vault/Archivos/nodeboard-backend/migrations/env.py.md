**Ruta:** `nodeboard-backend/migrations/env.py`

## Responsabilidad
Script de entorno de Alembic. Configura la conexión a la base de datos (leyendo `NODEBOARD_DB`
como fuente de verdad), importa los modelos SQLAlchemy reales del proyecto (`app.models`)
para que `autogenerate` pueda comparar el metadata declarativo contra la base de datos,
y ejecuta las migraciones en modo online (con engine) u offline (solo URL).

## Comportamiento
1. Agrega `nodeboard-backend/` a `sys.path` para poder importar `app.*` (necesario cuando Alembic se ejecuta desde el proyecto raíz, como ocurre en el lifespan de FastAPI)
2. Lee `NODEBOARD_DB` del entorno (fallback: `sqlite:///./nodeboard.db`) y lo inyecta como `sqlalchemy.url` — misma fuente que `app.database.DATABASE_URL`
3. Importa `app.database.Base` → `target_metadata = Base.metadata`
4. Importa `app.models` para que todos los modelos (Studio, Folder, Board, Node, Edge) se registren en `Base.metadata`
5. `run_migrations_offline()`: genera SQL sin conectar a la BD (útil para revisar)
6. `run_migrations_online()`: conecta y ejecuta las migraciones contra la BD real

## Exporta
- (nada directamente) — invocado por `alembic` CLI o por `alembic.command.upgrade` desde el lifespan

## Importa
- `app.database` — `Base` (metadata declarativa)
- `app.models` — efectos secundarios: registra modelos en `Base.metadata`
- Librerías externas: `os`, `sys`, `logging.config`, `sqlalchemy`, `alembic`

## Importado por
- `alembic` CLI (a través de `alembic.ini`)
- [[../Archivos/nodeboard-backend/app/main.py.md]] — `command.upgrade(Config("alembic.ini"), "head")` en el lifespan
