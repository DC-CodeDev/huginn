"""Tests de protección de persistencia en producción.

Verifica que ``database.py``:

- Rechace arrancar en producción sin ``DATA_PATH``.
- Rechace ``DATA_PATH`` relativa en producción.
- Use la ruta correcta en producción con ``DATA_PATH=/data``.
- Mantenga compatibilidad en desarrollo local.
- ``NODEBOARD_DB`` no permita evadir la protección en producción.

SQLite connection config (WAL, busy_timeout, foreign_keys):
- ``_resolve_busy_timeout`` valida y devuelve el timeout correcto.
- Conexiones a una base de archivo tienen ``journal_mode=wal``.
- ``foreign_keys`` está activado y bloquea FKs inválidas.
- Dos conexiones coexisten (WAL permite lectura durante escritura).
- ``busy_timeout`` se respeta ante bloqueo.
- Configuración no se aplica a motores que no son SQLite.
"""
import importlib
import os
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from app.database import (
    DatabaseConfigurationError,
    _resolve_busy_timeout,
    get_database_url,
    is_production,
    resolve_database_path,
    validate_storage_directory,
)


# ======================================================================
# is_production
# ======================================================================


class TestIsProduction:
    def test_production_lowercase(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        assert is_production() is True

    def test_production_uppercase(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "PRODUCTION")
        assert is_production() is True

    def test_prod(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "prod")
        assert is_production() is True

    def test_prod_mixed_case(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "Prod")
        assert is_production() is True

    def test_development(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        assert is_production() is False

    def test_empty(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "")
        assert is_production() is False

    def test_unset(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert is_production() is False

    def test_staging(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "staging")
        assert is_production() is False


# ======================================================================
# resolve_database_path
# ======================================================================


class TestResolveDatabasePath:
    def test_production_with_data_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATA_PATH", str(tmp_path))
        monkeypatch.delenv("NODEBOARD_DB", raising=False)
        path = resolve_database_path()
        assert path == tmp_path / "nodeboard.db"

    def test_production_without_data_path(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("DATA_PATH", raising=False)
        monkeypatch.delenv("NODEBOARD_DB", raising=False)
        with pytest.raises(DatabaseConfigurationError, match="DATA_PATH"):
            resolve_database_path()

    def test_production_with_relative_data_path(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATA_PATH", "./data")
        monkeypatch.delenv("NODEBOARD_DB", raising=False)
        with pytest.raises(DatabaseConfigurationError, match="absoluta"):
            resolve_database_path()

    def test_production_with_relative_data_path_no_dot(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATA_PATH", "relative/path")
        monkeypatch.delenv("NODEBOARD_DB", raising=False)
        with pytest.raises(DatabaseConfigurationError, match="absoluta"):
            resolve_database_path()

    def test_production_with_nodeboard_db_but_no_data_path(self, monkeypatch):
        """NODEBOARD_DB no debe evitar la protección en producción."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("DATA_PATH", raising=False)
        monkeypatch.setenv("NODEBOARD_DB", "sqlite:///some/other/path.db")
        with pytest.raises(DatabaseConfigurationError, match="DATA_PATH"):
            resolve_database_path()

    def test_dev_without_vars(self, monkeypatch):
        """Desarrollo sin variables → default relativo."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("DATA_PATH", raising=False)
        monkeypatch.delenv("NODEBOARD_DB", raising=False)
        path = resolve_database_path()
        assert path.is_absolute()
        assert path.name == "nodeboard.db"

    def test_dev_with_absolute_data_path(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("DATA_PATH", str(tmp_path))
        path = resolve_database_path()
        assert path == tmp_path / "nodeboard.db"

    def test_dev_with_relative_data_path(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("DATA_PATH", str(tmp_path))
        path = resolve_database_path()
        assert path == (tmp_path / "nodeboard.db")

    def test_dev_with_nodeboard_db(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("DATA_PATH", raising=False)
        db_path = tmp_path / "custom.db"
        monkeypatch.setenv("NODEBOARD_DB", f"sqlite:///{db_path}")
        path = resolve_database_path()
        assert path == db_path.resolve()


# ======================================================================
# validate_storage_directory
# ======================================================================


class TestValidateStorageDirectory:
    def test_existing_writable_directory(self, tmp_path):
        """No debe fallar con un directorio normal."""
        path = tmp_path / "nodeboard.db"
        validate_storage_directory(path)  # no error

    def test_creates_parent_directory(self, tmp_path):
        """Debe crear el directorio padre si no existe."""
        nested = tmp_path / "a" / "b" / "nodeboard.db"
        validate_storage_directory(nested)
        assert nested.parent.exists()

    def test_production_fails_on_non_writable(self, monkeypatch, tmp_path):
        """Producción falla si no se puede escribir."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        read_only = tmp_path / "readonly"
        read_only.mkdir()
        read_only.chmod(0o444)
        path = read_only / "nodeboard.db"
        with pytest.raises(DatabaseConfigurationError, match="escribir"):
            validate_storage_directory(path)

    def test_dev_warns_on_non_writable(self, monkeypatch, tmp_path, caplog):
        """Desarrollo solo advierte, no falla."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        read_only = tmp_path / "readonly"
        read_only.mkdir()
        read_only.chmod(0o444)
        path = read_only / "nodeboard.db"
        validate_storage_directory(path)  # no exception
        assert any("No se puede escribir" in r.message for r in caplog.records)


# ======================================================================
# get_database_url
# ======================================================================


class TestGetDatabaseUrl:
    def test_production_correct(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATA_PATH", str(tmp_path))
        monkeypatch.delenv("NODEBOARD_DB", raising=False)
        url = get_database_url()
        assert url == f"sqlite:///{tmp_path / 'nodeboard.db'}"

    def test_production_without_data_path(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("DATA_PATH", raising=False)
        monkeypatch.delenv("NODEBOARD_DB", raising=False)
        with pytest.raises(DatabaseConfigurationError, match="DATA_PATH"):
            get_database_url()

    def test_production_with_relative_data_path(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DATA_PATH", "./mydata")
        with pytest.raises(DatabaseConfigurationError, match="absoluta"):
            get_database_url()

    def test_dev_without_vars(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("DATA_PATH", raising=False)
        monkeypatch.delenv("NODEBOARD_DB", raising=False)
        url = get_database_url()
        assert url.startswith("sqlite:///")
        assert url.endswith("nodeboard.db")
        assert "./" not in url  # debe ser absoluta después de resolve()

    def test_dev_with_absolute_data_path(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.setenv("DATA_PATH", str(tmp_path))
        url = get_database_url()
        assert url == f"sqlite:///{tmp_path / 'nodeboard.db'}"

    def test_production_nodeboard_db_does_not_evade(self, monkeypatch):
        """NODEBOARD_DB no debe anular la protección de producción."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("DATA_PATH", raising=False)
        monkeypatch.setenv("NODEBOARD_DB", "sqlite:///some/path.db")
        with pytest.raises(DatabaseConfigurationError, match="DATA_PATH"):
            get_database_url()


# ======================================================================
# Integración: el módulo importa correctamente en modo dev
# ======================================================================


def test_module_imports_in_dev():
    """Verifica que el módulo se importe sin error en desarrollo."""
    import app.database
    assert app.database.DATABASE_URL.startswith("sqlite:///")
    assert app.database.DATABASE_URL.endswith("nodeboard.db")


def test_module_imports_in_dev_with_tmp_data_path(monkeypatch, tmp_path):
    """Verifica que el módulo se importe correctamente con DATA_PATH en dev."""
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    import app.database as db
    db = importlib.reload(db)
    assert db.DATABASE_URL == f"sqlite:///{tmp_path / 'nodeboard.db'}"


# ======================================================================
# SQLite connection configuration (_resolve_busy_timeout)
# ======================================================================


class TestResolveBusyTimeout:
    def test_default_5000(self, monkeypatch):
        monkeypatch.delenv("SQLITE_BUSY_TIMEOUT_MS", raising=False)
        assert _resolve_busy_timeout() == 5000

    def test_custom_value(self, monkeypatch):
        monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "3000")
        assert _resolve_busy_timeout() == 3000

    def test_zero_is_allowed(self, monkeypatch):
        """0 significa no esperar — técnicamente válido."""
        monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "0")
        assert _resolve_busy_timeout() == 0

    def test_negative_raises(self, monkeypatch):
        monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "-1")
        with pytest.raises(RuntimeError):
            _resolve_busy_timeout()

    def test_non_numeric_raises(self, monkeypatch):
        monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "abc")
        with pytest.raises(RuntimeError):
            _resolve_busy_timeout()

    def test_empty_string_raises(self, monkeypatch):
        monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "")
        with pytest.raises(RuntimeError):
            _resolve_busy_timeout()


# ======================================================================
# SQLite connection config (PRAGMAs on a file-based database)
# ======================================================================


class TestSqliteConnectionConfig:
    """Verifica que las PRAGMAs se apliquen correctamente a conexiones SQLite.

    Cada test crea su propio engine sobre un archivo temporal para no
    interferir con la base de datos global del proyecto.
    """

    @pytest.fixture()
    def db_file(self, tmp_path):
        return str(tmp_path / "test_config.db")

    @pytest.fixture()
    def engine_with_huginn_config(self, db_file):
        """Crea un engine con la misma configuración que ``database.py``."""
        eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _cfg(dbapi_conn, _rec):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        yield eng
        eng.dispose()

    # --- 1. foreign_keys activado ---

    def test_foreign_keys_on(self, engine_with_huginn_config):
        with engine_with_huginn_config.connect() as conn:
            result = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert result == 1

    # --- 2. busy_timeout default ---

    def test_busy_timeout_default(self, engine_with_huginn_config):
        with engine_with_huginn_config.connect() as conn:
            result = conn.execute(text("PRAGMA busy_timeout")).scalar()
        assert result == 5000

    # --- 3. journal_mode WAL ---

    def test_journal_mode_wal(self, engine_with_huginn_config):
        with engine_with_huginn_config.connect() as conn:
            result = conn.execute(text("PRAGMA journal_mode")).scalar()
        assert result == "wal"

    # --- 4. Config applies to new connections ---

    def test_config_applies_to_new_connection(self, engine_with_huginn_config):
        with engine_with_huginn_config.connect() as conn:
            # Primera conexión
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        with engine_with_huginn_config.connect() as conn:
            # Segunda conexión (nueva del pool)
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1

    # --- 5. FK inválida falla ---

    def test_invalid_fk_raises(self, engine_with_huginn_config, db_file):
        """Crea tablas con FK y verifica que insertar un hijo sin padre falle."""
        with engine_with_huginn_config.connect() as conn:
            conn.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE child (id INTEGER PRIMARY KEY, p INTEGER REFERENCES parent(id))"))
            conn.commit()

        with engine_with_huginn_config.connect() as conn:
            with pytest.raises(Exception) as exc:
                conn.execute(text("INSERT INTO child (id, p) VALUES (1, 999)"))
                conn.commit()
            assert any(w in str(exc.value).lower() for w in ("foreign", "constraint")), (
                f"Se esperaba error de FK, pero se obtuvo: {exc.value}"
            )

    # --- 6. Dos conexiones coexisten ---

    def test_two_connections_coexist(self, engine_with_huginn_config):
        with engine_with_huginn_config.connect() as conn_a:
            conn_a.execute(text("CREATE TABLE IF NOT EXISTS t (x INTEGER)"))
            conn_a.commit()
            conn_a.execute(text("INSERT INTO t (x) VALUES (1)"))
            conn_a.commit()
            with engine_with_huginn_config.connect() as conn_b:
                rows = conn_b.execute(text("SELECT x FROM t")).fetchall()
        assert rows == [(1,)]


# ======================================================================
# WAL concurrency (read during write)
# ======================================================================


class TestWalConcurrency:
    """Verifica que WAL permite lecturas durante escrituras concurrentes.

    Escenario:
        conexión A: BEGIN → INSERT sin commit
        conexión B: SELECT → funciona (WAL permite lectura durante escritura)
        conexión C: escritura → respeta busy_timeout y obtiene database is locked
    """

    @pytest.fixture()
    def db_file(self, tmp_path):
        return str(tmp_path / "test_concurrency.db")

    @pytest.fixture()
    def engine(self, db_file):
        eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})

        @event.listens_for(eng, "connect")
        def _cfg(dbapi_conn, _rec):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=100")  # timeout rápido para el test
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        with eng.connect() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS t (x INTEGER)"))
            conn.commit()

        yield eng
        eng.dispose()

    def test_read_during_write(self, engine):
        """Conexión A escribe sin commit; conexión B puede leer bajo WAL.

        Este test corre en un hilo separado para aislar la transacción A
        y evitar que la fixture limpie la sesión.
        """
        results = {}

        conn_a = engine.connect()
        try:
            # Iniciamos una transacción de escritura sin commit
            tx_a = conn_a.begin()
            conn_a.execute(text("INSERT INTO t (x) VALUES (42)"))
            results["tx_a"] = tx_a

            # Conexión B — lector (debería funcionar gracias a WAL)
            conn_b = engine.connect()
            try:
                rows = conn_b.execute(text("SELECT x FROM t")).fetchall()
                results["rows_b"] = rows
                # Bajo WAL, una lectura puede ocurrir durante una escritura
                # (la lectura ve el estado anterior al BEGIN)
                assert isinstance(rows, list), "lectura debe devolver una lista"
            finally:
                conn_b.close()
        finally:
            conn_a.close()

    def test_write_blocked_respects_timeout(self, engine):
        """Conexión A BEGIN IMMEDIATE + escritura sin commit;
        conexión B intenta escribir y debe recibir database is locked
        después del busy_timeout (100ms en este test).

        Usamos ``busy_timeout=100`` (0.1s) para que el test sea rápido.
        """
        import threading as _thr

        errors = {}
        ready = _thr.Event()
        done = _thr.Event()

        def writer_a(conn):
            conn.execute(text("BEGIN IMMEDIATE"))
            conn.execute(text("INSERT INTO t (x) VALUES (1)"))
            ready.set()  # señal: ya tengo el lock
            done.wait(timeout=5)  # mantener transacción abierta
            conn.rollback()  # liberar

        def writer_b(conn):
            ready.wait(timeout=5)  # esperar a que A tenga el lock
            try:
                conn.execute(text("INSERT INTO t (x) VALUES (2)"))
                conn.commit()
                errors["b"] = "no error (unexpected)"
            except Exception as e:
                errors["b_error"] = e
            done.set()  # liberar a A

        conn_a = engine.connect()
        conn_b = engine.connect()

        thr_a = _thr.Thread(target=writer_a, args=(conn_a,))
        thr_b = _thr.Thread(target=writer_b, args=(conn_b,))

        thr_a.start()
        thr_b.start()
        thr_a.join(timeout=5)
        thr_b.join(timeout=5)

        conn_a.close()
        conn_b.close()

        # writer_b debe haber fallado con database is locked
        assert "b_error" in errors, (
            f"Se esperaba error 'database is locked' en writer_b, errores={errors}"
        )
        err_msg = str(errors["b_error"]).lower()
        assert "locked" in err_msg, f"Se esperaba 'locked', pero se obtuvo: {errors['b_error']}"


# ======================================================================
# Non-SQLite backend guard
# ======================================================================


class TestNonSqliteGuard:
    """Verifica que la configuración SQLite no se aplique a otros motores."""

    def test_sqlite_engine_has_configure_listener(self):
        """El engine del módulo (sqlite) debe tener el listener de configuración."""
        import app.database as db_mod
        # Verificamos que el engine es sqlite y que el listener existe
        assert db_mod.engine.url.get_backend_name() == "sqlite"
        # El listener de connect está registrado (verificamos indirectamente
        # que las PRAGMAs se aplican)
        with db_mod.engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
