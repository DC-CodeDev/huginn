"""Tests de esquema y migración de MCP Tokens.

Verifica que la tabla mcp_tokens se cree correctamente,
con sus constraints, índices y FK, y que la migración
Alembic (upgrade/downgrade/upgrade) sea limpia.
"""
import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import MCPToken, User


def _run_upgrade_via_alembic(tmp_path):
    """Ejecuta todas las migraciones sobre una base temporal."""
    from alembic.config import Config
    from alembic.command import upgrade

    old_data = os.environ.get("DATA_PATH")
    old_nodeboard = os.environ.get("NODEBOARD_DB")
    try:
        os.environ["DATA_PATH"] = str(tmp_path)
        os.environ.pop("NODEBOARD_DB", None)
        ini_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        )
        cfg = Config(ini_path)
        upgrade(cfg, "head")
    finally:
        if old_data:
            os.environ["DATA_PATH"] = old_data
        else:
            os.environ.pop("DATA_PATH", None)
        if old_nodeboard:
            os.environ["NODEBOARD_DB"] = old_nodeboard


def _run_downgrade_via_alembic(tmp_path, target="-1"):
    from alembic.config import Config
    from alembic.command import downgrade

    old_data = os.environ.get("DATA_PATH")
    old_nodeboard = os.environ.get("NODEBOARD_DB")
    try:
        os.environ["DATA_PATH"] = str(tmp_path)
        os.environ.pop("NODEBOARD_DB", None)
        ini_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        )
        cfg = Config(ini_path)
        downgrade(cfg, target)
    finally:
        if old_data:
            os.environ["DATA_PATH"] = old_data
        else:
            os.environ.pop("DATA_PATH", None)
        if old_nodeboard:
            os.environ["NODEBOARD_DB"] = old_nodeboard


# ======================================================================
# Test Schema via ORM (creates tables with create_all)
# ======================================================================


@pytest.fixture()
def db_session(tmp_path):
    """Crea un engine + sesión sobre una base temporal, con todas las tablas creadas."""
    db_path = tmp_path / "nodeboard.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @sa_event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class TestSchema:
    def test_table_created(self, db_session):
        engine = db_session.get_bind()
        assert "mcp_tokens" in inspect(engine).get_table_names()

    def test_foreign_key_to_users(self, db_session):
        engine = db_session.get_bind()
        fks = inspect(engine).get_foreign_keys("mcp_tokens")
        user_fk = [fk for fk in fks if fk["constrained_columns"] == ["user_id"]]
        assert len(user_fk) >= 1
        assert "users" in user_fk[0]["referred_table"]

    def test_foreign_key_cascade(self, db_session):
        u = User(id="user1", email="test@example.com", name="Test", auth_provider="google")
        db_session.add(u)
        db_session.commit()

        t = MCPToken(
            id="token1",
            user_id=u.id,
            name="Test",
            token_prefix="huginn_mcp_abc123",
            token_hash="a" * 64,
            scopes=["studios:read"],
        )
        db_session.add(t)
        db_session.commit()
        assert db_session.query(MCPToken).count() == 1

        db_session.delete(u)
        db_session.commit()
        assert db_session.query(MCPToken).count() == 0

    def test_index_on_user_id(self, db_session):
        engine = db_session.get_bind()
        indexes = inspect(engine).get_indexes("mcp_tokens")
        assert any("user_id" in idx.get("column_names", []) for idx in indexes)

    def test_token_hash_unique(self, db_session):
        engine = db_session.get_bind()
        indexes = inspect(engine).get_indexes("mcp_tokens")
        hash_idx = [idx for idx in indexes if "token_hash" in idx.get("column_names", [])]
        assert len(hash_idx) >= 1
        assert hash_idx[0].get("unique", False)

    def test_scopes_persist(self, db_session):
        u = User(id="user2", email="t2@example.com", name="T2", auth_provider="google")
        db_session.add(u)
        db_session.commit()
        t = MCPToken(
            id="token2", user_id=u.id, name="T", token_prefix="hp_abc",
            token_hash="b" * 64, scopes=["studios:read", "boards:read"],
        )
        db_session.add(t)
        db_session.commit()
        assert db_session.get(MCPToken, "token2").scopes == ["studios:read", "boards:read"]

    def test_constraints_nullable(self, db_session):
        engine = db_session.get_bind()
        cols = {c["name"]: c for c in inspect(engine).get_columns("mcp_tokens")}
        assert cols["constraints"]["nullable"]

    def test_timestamps_accept_values(self, db_session):
        """created_at obligatorio; last_used_at/expires_at/revoked_at opcionales."""
        engine = db_session.get_bind()
        cols = {c["name"]: c for c in inspect(engine).get_columns("mcp_tokens")}
        assert not cols["created_at"]["nullable"]
        assert cols["last_used_at"]["nullable"]
        assert cols["expires_at"]["nullable"]
        assert cols["revoked_at"]["nullable"]


# ======================================================================
# Test Migration Script (upgrade / downgrade via alembic)
# ======================================================================


class TestMigrationScript:
    def test_upgrade_creates_table(self, tmp_path):
        _run_upgrade_via_alembic(tmp_path)
        db_path = tmp_path / "nodeboard.db"
        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_tokens" in inspect(engine).get_table_names()
        engine.dispose()

    def test_upgrade_downgrade_upgrade(self, tmp_path):
        _run_upgrade_via_alembic(tmp_path)
        db_path = tmp_path / "nodeboard.db"

        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_tokens" in inspect(engine).get_table_names()
        engine.dispose()

        _run_downgrade_via_alembic(tmp_path)

        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_tokens" not in inspect(engine).get_table_names()
        engine.dispose()

        _run_upgrade_via_alembic(tmp_path)

        engine = create_engine(f"sqlite:///{db_path}")
        assert "mcp_tokens" in inspect(engine).get_table_names()
        engine.dispose()

    def test_other_tables_not_altered(self, tmp_path):
        _run_upgrade_via_alembic(tmp_path)
        db_path = tmp_path / "nodeboard.db"
        engine = create_engine(f"sqlite:///{db_path}")
        tables = set(inspect(engine).get_table_names())
        expected = {"users", "sessions", "studios", "folders", "boards", "nodes", "edges", "mcp_tokens"}
        for t in expected:
            assert t in tables, f"Falta {t}"
        extra = tables - expected - {"alembic_version"}
        assert not extra, f"Tablas extra: {extra}"
        engine.dispose()
