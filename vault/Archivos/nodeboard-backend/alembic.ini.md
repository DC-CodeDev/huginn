**Ruta:** `nodeboard-backend/alembic.ini`

## Responsabilidad
Archivo de configuración de Alembic. Define la ruta a los scripts de migración (`migrations/`),
la URL de base de datos (sobreescrita dinámicamente por `env.py` desde `NODEBOARD_DB`),
y la configuración de logging.

## Comportamiento
- `script_location = %(here)s/migrations` — apunta al directorio de migraciones (relativo al propio `.ini`)
- `prepend_sys_path = .` — agrega el CWD a `sys.path` (útil al correr `alembic` CLI desde `nodeboard-backend/`)
- `sqlalchemy.url` — placeholder; `env.py` lo sobreescribe en tiempo de ejecución desde la variable de entorno `NODEBOARD_DB` (misma fuente que `app.database.DATABASE_URL`)
- Logging: `INFO` para alembic, `WARNING` para root y sqlalchemy

## Importado por
- [[../Archivos/nodeboard-backend/app/main.py.md]] — `Config(alembic.ini)` en el lifespan para ejecutar `alembic upgrade head`
- [[../Archivos/nodeboard-backend/migrations/env.py.md]] — lectura vía `context.config` (proporcionado por la CLI o por `Config` desde main.py)
