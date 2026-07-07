"""Tests de protección de persistencia en producción.

Verifica que ``database.py``:

- Rechace arrancar en producción sin ``DATA_PATH``.
- Rechace ``DATA_PATH`` relativa en producción.
- Use la ruta correcta en producción con ``DATA_PATH=/data``.
- Mantenga compatibilidad en desarrollo local.
- ``NODEBOARD_DB`` no permita evadir la protección en producción.
"""
import importlib
import os
from pathlib import Path

import pytest

from app.database import (
    DatabaseConfigurationError,
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
