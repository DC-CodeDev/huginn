"""Tests unitarios del servicio de tags de Board.

Cubre: tags de board propio/ajeno/inexistente/vacío, deduplicación
(intra-node e inter-node), orden, manejo de nulos, vacíos, mayúsculas,
y verificación de que las lecturas no hacen commit ni modifican datos.
"""
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Board, Node, Studio, User
from app.services.errors import ResourceNotFound
from app.services.tags import list_board_tags


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        try:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def _user(db, email=None) -> User:
    u = User(
        id=uuid.uuid4().hex[:16],
        email=email or f"{uuid.uuid4().hex}@example.com",
        name="Test",
        auth_provider="google",
    )
    db.add(u)
    db.commit()
    return u


def _studio(db, user) -> Studio:
    st = Studio(id=uuid.uuid4().hex[:16], name="S", color="azul", user_id=user.id)
    db.add(st)
    db.commit()
    return st


def _board(db, user, studio=None) -> Board:
    st = studio or _studio(db, user)
    b = Board(id=uuid.uuid4().hex[:16], name="B", studio_id=st.id)
    db.add(b)
    db.commit()
    return b


def _node(db, board, node_id="n1", tags=None):
    """Crea un node con tags opcionales."""
    n = Node(id=node_id, board_id=board.id, tags=tags or [])
    db.add(n)
    db.commit()
    return n


# ======================================================================
# tests básicos
# ======================================================================


def test_own_board_returns_tags(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1", tags=["alpha", "beta"])
    result = list_board_tags(db, u.id, b.id)
    assert result == ["alpha", "beta"]


def test_other_board_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    b = _board(db, a)
    _node(db, b, "n1", tags=["x"])
    with pytest.raises(ResourceNotFound):
        list_board_tags(db, b_user.id, b.id)


def test_nonexistent_board_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        list_board_tags(db, u.id, "no-such-id")


def test_empty_board_returns_empty(db):
    u = _user(db)
    b = _board(db, u)
    assert list_board_tags(db, u.id, b.id) == []


# ======================================================================
# manejo de nulos y vacíos
# ======================================================================


def test_node_without_tags_does_not_break(db):
    u = _user(db)
    b = _board(db, u)
    # Node con tags=None (valor por defecto)
    Node(id="n1", board_id=b.id)
    db.commit()
    assert list_board_tags(db, u.id, b.id) == []


def test_tags_none_does_not_add_element(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1", tags=None)
    assert list_board_tags(db, u.id, b.id) == []


def test_empty_tags_list_does_not_add_elements(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1", tags=[])
    assert list_board_tags(db, u.id, b.id) == []


# ======================================================================
# deduplicación
# ======================================================================


def test_duplicate_tags_within_node_deduplicated(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1", tags=["alpha", "beta", "alpha"])
    result = list_board_tags(db, u.id, b.id)
    assert result == ["alpha", "beta"]


def test_duplicate_tags_across_nodes_deduplicated(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1", tags=["alpha", "beta"])
    _node(db, b, "n2", tags=["beta", "gamma"])
    result = list_board_tags(db, u.id, b.id)
    assert result == ["alpha", "beta", "gamma"]


def test_distinct_tags_preserved(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1", tags=["x", "y"])
    _node(db, b, "n2", tags=["z"])
    result = list_board_tags(db, u.id, b.id)
    assert result == ["x", "y", "z"]


# ======================================================================
# orden (case-insensitive)
# ======================================================================


def test_order_is_case_insensitive_sorted(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1", tags=["Beta", "alpha", "Zeta"])
    result = list_board_tags(db, u.id, b.id)
    assert result == ["alpha", "Beta", "Zeta"]


# ======================================================================
# no efectos secundarios
# ======================================================================


def test_does_not_commit(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1", tags=["tag"])
    list_board_tags(db, u.id, b.id)
    db.rollback()
    assert list_board_tags(db, u.id, b.id) == ["tag"]


def test_does_not_modify_updated_at(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1", tags=["x"])
    before = b.updated_at
    list_board_tags(db, u.id, b.id)
    db.expire_all()
    loaded = db.get(Board, b.id)
    assert loaded.updated_at == before


def test_does_not_modify_nodes(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1", tags=["original"])
    list_board_tags(db, u.id, b.id)
    db.expire_all()
    node = db.get(Node, "n1")
    assert node.tags == ["original"]


# ======================================================================
# aislamiento
# ======================================================================


def test_one_board_does_not_include_other_board_tags(db):
    u = _user(db)
    b1 = _board(db, u)
    b2 = _board(db, u)
    _node(db, b1, "n1", tags=["solo-b1"])
    _node(db, b2, "n2", tags=["solo-b2"])
    assert list_board_tags(db, u.id, b1.id) == ["solo-b1"]
    assert list_board_tags(db, u.id, b2.id) == ["solo-b2"]


def test_one_user_does_not_get_other_user_tags(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    ba = _board(db, a)
    _node(db, ba, "n1", tags=["de-a"])
    with pytest.raises(ResourceNotFound):
        list_board_tags(db, b_user.id, ba.id)
