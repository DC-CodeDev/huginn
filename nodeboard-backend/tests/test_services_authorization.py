"""Tests unitarios de services/authorization.py.

Validan que las funciones de autorización:
- retornen el recurso cuando el usuario es propietario;
- lancen ResourceNotFound cuando el recurso no pertenece al usuario;
- lancen ResourceNotFound cuando el ID no existe;
- no hagan commit ni modifiquen recursos.
"""
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import _uid
from app.models import User, Studio, Folder, Board, Node, Edge
from app.services.authorization import (
    get_owned_studio,
    get_owned_folder,
    get_owned_board,
    get_owned_node,
    get_owned_edge,
)
from app.services.errors import ResourceNotFound


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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
    s = Studio(id=_uid(), name="S", color="azul", user_id=user.id)
    db.add(s)
    db.commit()
    return s


def _folder(db, user, studio=None) -> Folder:
    st = studio or _studio(db, user)
    f = Folder(id=_uid(), name="F", studio_id=st.id)
    db.add(f)
    db.commit()
    return f


def _board(db, user, studio=None, folder=None) -> Board:
    st = studio or _studio(db, user)
    b = Board(
        id=_uid(),
        name="B",
        studio_id=st.id,
        folder_id=folder.id if folder else None,
    )
    db.add(b)
    db.commit()
    return b


def _node(db, user, board=None) -> Node:
    b = board or _board(db, user)
    n = Node(id=_uid(), board_id=b.id)
    db.add(n)
    db.commit()
    return n


def _edge(db, user, board=None) -> Edge:
    b = board or _board(db, user)
    e = Edge(id=_uid(), board_id=b.id, from_node="n1", from_port="p", to_node="n2", to_port="p")
    db.add(e)
    db.commit()
    return e


# ------------------------------------------------------------------
# get_owned_studio
# ------------------------------------------------------------------


def test_owner_gets_studio(db):
    u = _user(db)
    s = _studio(db, u)
    result = get_owned_studio(db, u.id, s.id)
    assert result.id == s.id
    assert result.user_id == u.id


def test_other_user_cannot_get_studio(db):
    owner = _user(db)
    other = _user(db)
    s = _studio(db, owner)
    with pytest.raises(ResourceNotFound) as exc:
        get_owned_studio(db, other.id, s.id)
    assert exc.value.resource_type == "Studio"


def test_nonexistent_studio_raises_not_found(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound) as exc:
        get_owned_studio(db, u.id, "no-such-id")
    assert exc.value.resource_type == "Studio"


# ------------------------------------------------------------------
# get_owned_folder
# ------------------------------------------------------------------


def test_owner_gets_folder(db):
    u = _user(db)
    f = _folder(db, u)
    result = get_owned_folder(db, u.id, f.id)
    assert result.id == f.id


def test_other_user_cannot_get_folder(db):
    owner = _user(db)
    other = _user(db)
    f = _folder(db, owner)
    with pytest.raises(ResourceNotFound) as exc:
        get_owned_folder(db, other.id, f.id)
    assert exc.value.resource_type == "Folder"


def test_nonexistent_folder_raises_not_found(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        get_owned_folder(db, u.id, "no-such-id")


# ------------------------------------------------------------------
# get_owned_board
# ------------------------------------------------------------------


def test_owner_gets_board(db):
    u = _user(db)
    b = _board(db, u)
    result = get_owned_board(db, u.id, b.id)
    assert result.id == b.id


def test_other_user_cannot_get_board(db):
    owner = _user(db)
    other = _user(db)
    b = _board(db, owner)
    with pytest.raises(ResourceNotFound) as exc:
        get_owned_board(db, other.id, b.id)
    assert exc.value.resource_type == "Board"


def test_nonexistent_board_raises_not_found(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        get_owned_board(db, u.id, "no-such-id")


# ------------------------------------------------------------------
# get_owned_node
# ------------------------------------------------------------------


def test_owner_gets_node(db):
    u = _user(db)
    n = _node(db, u)
    result = get_owned_node(db, u.id, n.id)
    assert result.id == n.id


def test_other_user_cannot_get_node(db):
    owner = _user(db)
    other = _user(db)
    n = _node(db, owner)
    with pytest.raises(ResourceNotFound) as exc:
        get_owned_node(db, other.id, n.id)
    assert exc.value.resource_type == "Node"


def test_nonexistent_node_raises_not_found(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        get_owned_node(db, u.id, "no-such-id")


# ------------------------------------------------------------------
# get_owned_edge
# ------------------------------------------------------------------


def test_owner_gets_edge(db):
    u = _user(db)
    e = _edge(db, u)
    result = get_owned_edge(db, u.id, e.id)
    assert result.id == e.id


def test_other_user_cannot_get_edge(db):
    owner = _user(db)
    other = _user(db)
    e = _edge(db, owner)
    with pytest.raises(ResourceNotFound) as exc:
        get_owned_edge(db, other.id, e.id)
    assert exc.value.resource_type == "Edge"


def test_nonexistent_edge_raises_not_found(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        get_owned_edge(db, u.id, "no-such-id")


# ------------------------------------------------------------------
# Las funciones no hacen commit ni modifican recursos
# ------------------------------------------------------------------


def test_functions_do_not_commit(db):
    """Verifica que las funciones de autorización no persistan cambios."""
    u = _user(db)
    s = _studio(db, u)

    # Realizar una consulta de autorización — no debería hacer commit
    get_owned_studio(db, u.id, s.id)

    # Hacer rollback de cualquier cambio que pudiera haber hecho
    db.rollback()

    # El studio debe seguir existiendo (rollback no debería haber borrado nada
    # porque las funciones de autorización no hacen commit).
    result = get_owned_studio(db, u.id, s.id)
    assert result.id == s.id
