"""Tests de aislamiento multi-usuario.

Verifica que Usuario A no puede leer, modificar ni borrar recursos de Usuario B,
en todas las rutas de negocio. Todos los IDs válidos de recursos ajenos deben
devolver 404 (nunca 403).
"""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import (
    board_tags,
    create_board,
    create_edge,
    create_folder,
    create_node,
    create_studio,
    delete_board,
    delete_edge,
    delete_folder,
    delete_node,
    delete_studio,
    get_board,
    list_boards,
    list_folder_boards,
    list_folders,
    list_studio_boards,
    list_studios,
    rename_board,
    save_board_state,
    update_edge,
    update_node,
)
from app.models import User
from app.schemas import (
    BoardCreate,
    BoardRename,
    BoardStateSave,
    EdgeCreateRequest,
    EdgeSchema,
    EdgeUpdate,
    EdgeUpdateRequest,
    FolderCreate,
    NodeCreateRequest,
    NodeSchema,
    NodeUpdate,
    NodeUpdateRequest,
    PortRef,
    StudioCreate,
)


@pytest.fixture()
def db():
    """Sesión aislada contra una SQLite temporal."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


def _user(db, email="a@test.com") -> User:
    u = User(
        id=uuid.uuid4().hex[:16],
        email=email,
        name="Test User",
        auth_provider="google",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def users(db):
    """Dos usuarios aislados: A (propietario) y B (intruso)."""
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    return a, b


def _full_scenario(db, user):
    """Crea Studio → Folder → Board → 2 Nodes → 1 Edge, todos del `user`.
    Devuelve {sid, fid, bid, n1, n2, e1}.
    """
    sid = create_studio(StudioCreate(name="S", color="azul"), db, current_user=user).id
    fid = create_folder(FolderCreate(name="F", studio_id=sid), db, current_user=user).id
    bid = create_board(BoardCreate(name="B", studio_id=sid, folder_id=fid), db, current_user=user).id
    n1 = create_node(bid, NodeCreateRequest(id="n1", expected_version=1), db, current_user=user)
    n2 = create_node(bid, NodeCreateRequest(id="n2", expected_version=2), db, current_user=user)
    e1 = create_edge(
        bid,
        EdgeCreateRequest(
            id="e1",
            from_=PortRef(nodeId="n1", portId="p"),
            to=PortRef(nodeId="n2", portId="p"),
            expected_version=3,
        ),
        db,
        current_user=user,
    )
    return {"sid": sid, "fid": fid, "bid": bid, "n1": n1, "n2": n2, "e1": e1}


def _assert_404(fn, *args, **kwargs):
    """Ejecuta fn(*args, **kwargs) y verifica que levanta HTTPException 404."""
    with pytest.raises(HTTPException) as exc:
        fn(*args, **kwargs)
    assert exc.value.status_code == 404, f"Esperaba 404, obtuvo {exc.value.status_code}"


# ------------------------------------------------------------------ Studio


def test_list_studios_isolation(db, users):
    a, b = users
    _full_scenario(db, a)
    assert len(list_studios(db, current_user=a)) == 1
    assert len(list_studios(db, current_user=b)) == 0


def test_delete_other_studio_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(delete_studio, r["sid"], db, current_user=b)
    # Aún existe para A
    assert len(list_studios(db, current_user=a)) == 1


# ---------------------------------------------------------------- Folders


def test_list_folders_other_studio_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    # B no puede ni listar las carpetas del studio de A
    _assert_404(list_folders, r["sid"], db, current_user=b)


def test_delete_other_folder_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(delete_folder, r["fid"], db, current_user=b)


def test_create_folder_in_other_studio_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(create_folder, FolderCreate(name="X", studio_id=r["sid"]), db, current_user=b)


# ---------------------------------------------------------------- Boards


def test_list_boards_isolation(db, users):
    a, b = users
    _full_scenario(db, a)
    assert len(list_boards(db, current_user=a)) == 1
    assert len(list_boards(db, current_user=b)) == 0


def test_get_other_board_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(get_board, r["bid"], db, current_user=b)


def test_list_studio_boards_other_studio_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(list_studio_boards, r["sid"], db, current_user=b)


def test_list_folder_boards_other_folder_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(list_folder_boards, r["fid"], db, current_user=b)


def test_create_board_in_other_studio_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(create_board, BoardCreate(name="X", studio_id=r["sid"]), db, current_user=b)


def test_rename_other_board_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(rename_board, r["bid"], BoardRename(name="Hackeado", expected_version=1), db, current_user=b)


def test_delete_other_board_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(delete_board, r["bid"], 1, db, current_user=b)


def test_save_board_state_other_board_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(
        save_board_state,
        r["bid"],
        BoardStateSave(nodes=[], edges=[], expected_version=1),
        db,
        current_user=b,
    )


def test_board_tags_other_board_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(board_tags, r["bid"], db, current_user=b)


# ---------------------------------------------------------------- Nodes


def test_create_node_other_board_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(create_node, r["bid"], NodeCreateRequest(id="x", expected_version=1), db, current_user=b)


def test_update_other_node_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(update_node, r["n1"].id, NodeUpdateRequest(title="X", expected_version=1), db, current_user=b)


def test_delete_other_node_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(delete_node, r["n1"].id, 1, db, current_user=b)


# ---------------------------------------------------------------- Edges


def test_create_edge_other_board_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(
        create_edge,
        r["bid"],
        EdgeCreateRequest(
            id="x",
            from_=PortRef(nodeId="n1", portId="p"),
            to=PortRef(nodeId="n2", portId="p"),
            expected_version=1,
        ),
        db,
        current_user=b,
    )


def test_update_other_edge_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(update_edge, r["e1"].id, EdgeUpdateRequest(label="hack", expected_version=1), db, current_user=b)


def test_delete_other_edge_404(db, users):
    a, b = users
    r = _full_scenario(db, a)
    _assert_404(delete_edge, r["e1"].id, 1, db, current_user=b)
