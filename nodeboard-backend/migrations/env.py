"""
Alembic env.py — configurado para Huginn Nodeboard.

Lee la URL de la BD desde app.database.get_database_url() (misma fuente
que la app en runtime), e importa los modelos SQLAlchemy reales para que
autogenerate funcione contra el metadata declarativo del proyecto.
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Agrega el directorio raíz del backend a sys.path para que se puedan
# importar los módulos de `app` desde aquí.  La raíz es el parent de
# migrations/, que es nodeboard-backend/.
_be_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _be_dir not in sys.path:
    sys.path.insert(0, _be_dir)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url usando la misma función que usa la app en runtime,
# para que migrations y producción compartan la misma lógica de resolución.
from app.database import get_database_url  # noqa: E402
config.set_main_option("sqlalchemy.url", get_database_url())

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Importar los modelos para que se registren en Base.metadata.
# El import de models arrastra todas las subclases de Base.
from app.database import Base  # noqa: E402
import app.models  # noqa: E402 — asegura que los modelos se registren

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
