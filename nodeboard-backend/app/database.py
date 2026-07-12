"""Configuración de la base de datos (SQLite + SQLAlchemy 2.x).

En producción, la variable DATA_PATH es obligatoria y debe ser una ruta
absoluta a un directorio existente y escribible.  La base se crea en
``<DATA_PATH>/nodeboard.db``.

En desarrollo local se mantiene el default relativo ``./nodeboard.db``
(comportamiento histórico).
"""
import logging
import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers de entorno
# ---------------------------------------------------------------------------


def _normalise(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().lower()


def is_production() -> bool:
    """Retorna True si la variable ENVIRONMENT indica un entorno productivo.

    Valores aceptados (case-insensitive): ``production``, ``prod``.
    Cualquier otro valor (incluyendo ausencia de variable) se interpreta
    como desarrollo.
    """
    env = _normalise(os.getenv("ENVIRONMENT"))
    return env in ("production", "prod")


# ---------------------------------------------------------------------------
# resolución de ruta
# ---------------------------------------------------------------------------


class DatabaseConfigurationError(RuntimeError):
    """Error de configuración de la base de datos — siempre fatal en producción."""
    pass


def resolve_database_path() -> Path:
    """Resuelve la ruta absoluta del archivo de base de datos SQLite.

    Reglas
    ------
    1. **Producción**
       - ``DATA_PATH`` es obligatoria.
       - Debe ser una ruta absoluta.
       - Se construye ``Path(DATA_PATH) / "nodeboard.db"``.
       - Si ``DATA_PATH`` no está definida → ``DatabaseConfigurationError``.
       - Si la ruta no es absoluta → ``DatabaseConfigurationError``.

    2. **Desarrollo local**
       - Si ``DATA_PATH`` está definida (absoluta o relativa) se usa igual que
         en producción.
       - Si no, se usa la variable ``NODEBOARD_DB`` (legacy), o el default
         ``sqlite:///./nodeboard.db``.
       - ``NODEBOARD_DB`` **siempre incluye el prefijo** ``sqlite:///`` y el
         resto es la ruta.

    Returns
    -------
    Path
        Ruta absoluta al archivo ``.db`` (el archivo puede no existir aún).
    """
    data_path = os.getenv("DATA_PATH")

    if data_path:
        if is_production() and not os.path.isabs(data_path):
            raise DatabaseConfigurationError(
                f"DATA_PATH debe ser una ruta absoluta en producción, pero se recibió: {data_path}\n"
                "  Ejemplo correcto: DATA_PATH=/data"
            )
        p = Path(data_path) / "nodeboard.db"
        return p.resolve()

    # Producción sin DATA_PATH → error fatal
    if is_production():
        raise DatabaseConfigurationError(
            "Huginn no puede iniciar en producción sin DATA_PATH.\n"
            "  Configura DATA_PATH=/data y monta un volumen persistente en /data."
        )

    # Desarrollo: usar NODEBOARD_DB o default relativo
    db_url = os.getenv("NODEBOARD_DB", "sqlite:///./nodeboard.db")
    # sqlite:///path → extraer path
    raw_path = db_url.removeprefix("sqlite:///")
    return Path(raw_path).resolve()


def validate_storage_directory(path: Path) -> None:
    """Valida que el directorio padre de *path* exista y sea escribible.

    En producción eleva ``DatabaseConfigurationError`` si algo falla; en
    desarrollo solo advierte por log.

    La validación de escritura se hace con ``os.access(W_OK)`` y, si falla,
    se intenta crear un archivo temporal para confirmar (evita falsos
    positivos en NFS/FUSE).
    """
    parent = path.parent

    # 1. Crear el directorio si no existe (seguro: mkdir -p)
    if not parent.exists():
        try:
            parent.mkdir(parents=True, exist_ok=True)
            logger.info("huginn-storage: created directory %s", parent)
        except OSError as exc:
            msg = f"No se pudo crear el directorio {parent}: {exc}"
            if is_production():
                raise DatabaseConfigurationError(msg) from exc
            logger.warning("huginn-storage: %s", msg)
            return

    # 2. Verificar que sea un directorio
    if not parent.is_dir():
        msg = f"{parent} existe pero no es un directorio"
        if is_production():
            raise DatabaseConfigurationError(msg)
        logger.warning("huginn-storage: %s", msg)
        return

    # 3. Verificar permisos de escritura
    if os.access(parent, os.W_OK):
        return  # todo bien

    # 4. Fallback: intentar crear un archivo temporal (handle NFS/FUSE)
    try:
        tmp = tempfile.NamedTemporaryFile(dir=parent, delete=True)
        tmp.close()
    except OSError as exc:
        msg = f"No se puede escribir en {parent}: {exc}"
        if is_production():
            raise DatabaseConfigurationError(msg) from exc
        logger.warning("huginn-storage: %s", msg)


# ---------------------------------------------------------------------------
# logging de startup (una sola vez)
# ---------------------------------------------------------------------------


def _log_database_info(path: Path) -> None:
    """Registra diagnóstico de almacenamiento sin exponer secretos."""
    parent = path.parent
    lines = [
        f"huginn-storage: environment={'production' if is_production() else 'development'}",
        f"huginn-storage: database_path={path}",
        f"huginn-storage: directory_exists={parent.exists()}",
        f"huginn-storage: directory_writable={os.access(parent, os.W_OK) if parent.exists() else 'N/A'}",
        f"huginn-storage: database_exists={path.exists()}",
    ]
    if path.exists():
        lines.append(f"huginn-storage: database_size_bytes={path.stat().st_size}")
    for line in lines:
        logger.info(line)


# ---------------------------------------------------------------------------
# URL pública
# ---------------------------------------------------------------------------


def get_database_url() -> str:
    """Construye la URL de conexión SQLite con validaciones de producción.

    Returns
    -------
    str
        URL completa tipo ``sqlite:////data/nodeboard.db``.

    Raises
    ------
    DatabaseConfigurationError
        Si la configuración es inválida para el entorno actual.
    """
    # Resolver ruta (valida DATA_PATH y entorno)
    db_path = resolve_database_path()

    # Validar que el directorio padre exista y sea escribible
    validate_storage_directory(db_path)

    # Log de startup (una sola vez cuando se evalúa el módulo)
    _log_database_info(db_path)

    return f"sqlite:///{db_path}"


# ---------------------------------------------------------------------------
# SQLite busy timeout (desde variable de entorno)
# ---------------------------------------------------------------------------


def _resolve_busy_timeout() -> int:
    """Lee y valida ``SQLITE_BUSY_TIMEOUT_MS``.

    Returns
    -------
    int
        Milisegundos de busy timeout (default 5000).

    Raises
    ------
    DatabaseConfigurationError
        Si el valor no es un entero positivo.
    """
    raw = os.getenv("SQLITE_BUSY_TIMEOUT_MS", "5000")
    try:
        value = int(raw)
    except (ValueError, TypeError):
        raise DatabaseConfigurationError(
            f"SQLITE_BUSY_TIMEOUT_MS debe ser un entero, pero se recibió: {raw!r}"
        )
    if value < 0:
        raise DatabaseConfigurationError(
            f"SQLITE_BUSY_TIMEOUT_MS no puede ser negativo: {value}"
        )
    return value


# ---------------------------------------------------------------------------
# engine + sesión
# ---------------------------------------------------------------------------

DATABASE_URL = get_database_url()

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# ---------------------------------------------------------------------------
# configuración por conexión (solo SQLite)
# ---------------------------------------------------------------------------

if engine.url.get_backend_name() == "sqlite":
    _busy_timeout_ms = _resolve_busy_timeout()

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={_busy_timeout_ms}")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    logger.info(
        "[huginn-db] sqlite journal_mode=wal busy_timeout_ms=%d foreign_keys=on",
        _busy_timeout_ms,
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Dependencia de FastAPI: una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
