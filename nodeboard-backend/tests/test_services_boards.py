"""Tests unitarios del servicio de Boards.

Cubre listado (propio/ajeno/por folder/sin folder/orden), creación
(propia/ajena/validación Studio–Folder), lectura (propia/ajena/inexistente/
contenido completo), renombrado (propio/ajeno/inexistente/timestamp),
eliminación (propia/ajena/inexistente/cascada), resumen (conteos),
y verificación de que las lecturas no hacen commit.
"""
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Board, Edge, Folder, Node, Studio, User
from app.schemas import BoardCreate, BoardRename
from app.services.boards import (
    board_state,
    create_board,
    delete_board,
    get_board,
    list_boards,
    list_folder_boards,
    list_studio_boards,
    rename_board,
)
from app.services.errors import ResourceNotFound, ValidationFailure, VersionConflict


@pytest.fixture()
def db():
    """Sesión aislada contra una SQLite temporal con FK activadas."""
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


def _studio(db, user, name="Studio") -> Studio:
    st = Studio(id=uuid.uuid4().hex[:16], name=name, color="azul", user_id=user.id)
    db.add(st)
    db.commit()
    return st


def _folder(db, user, studio=None, name="Folder") -> Folder:
    st = studio or _studio(db, user)
    f = Folder(id=uuid.uuid4().hex[:16], name=name, studio_id=st.id)
    db.add(f)
    db.commit()
    return f


def _node_inside(db, board, node_id="n1") -> Node:
    n = Node(id=node_id, board_id=board.id)
    db.add(n)
    db.commit()
    return n


def _edge_inside(db, board, edge_id="e1") -> Edge:
    e = Edge(id=edge_id, board_id=board.id, from_node="n1", from_port="p", to_node="n2", to_port="p")
    db.add(e)
    db.commit()
    return e


# ======================================================================
# list_boards
# ======================================================================


def test_list_boards_returns_own_boards(db):
    u = _user(db)
    st = _studio(db, u)
    b1 = create_board(db, u.id, BoardCreate(name="B1", studio_id=st.id))
    b2 = create_board(db, u.id, BoardCreate(name="B2", studio_id=st.id))
    result = list_boards(db, u.id)
    assert len(result) == 2
    assert {r.name for r in result} == {"B1", "B2"}


def test_list_boards_excludes_other_user_boards(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    create_board(db, a.id, BoardCreate(name="De A", studio_id=st.id))
    assert len(list_boards(db, b.id)) == 0


def test_list_boards_ordered_by_updated_at_desc(db):
    u = _user(db)
    st = _studio(db, u)
    b1 = create_board(db, u.id, BoardCreate(name="Old", studio_id=st.id))
    # Pausa y crea otro
    import time
    time.sleep(0.01)
    b2 = create_board(db, u.id, BoardCreate(name="New", studio_id=st.id))
    # Renombrar el primero para que updated_at cambie
    rename_board(db, u.id, b1.id, BoardRename(name="Zeta", expected_version=1))
    result = list_boards(db, u.id)
    assert len(result) == 2
    # El más recientemente actualizado primero
    assert result[0].name == "Zeta"
    assert result[1].name == "New"


def test_list_boards_does_not_commit(db):
    u = _user(db)
    st = _studio(db, u)
    create_board(db, u.id, BoardCreate(name="B", studio_id=st.id))
    list_boards(db, u.id)
    db.rollback()
    assert len(list_boards(db, u.id)) == 1


# ======================================================================
# list_studio_boards
# ======================================================================


def test_list_studio_boards_returns_boards(db):
    u = _user(db)
    st = _studio(db, u)
    create_board(db, u.id, BoardCreate(name="B1", studio_id=st.id))
    create_board(db, u.id, BoardCreate(name="B2", studio_id=st.id))
    result = list_studio_boards(db, u.id, st.id)
    assert len(result.root_boards) == 2
    assert len(result.folder_boards) == 0


def test_list_studio_boards_separates_root_and_folder(db):
    u = _user(db)
    st = _studio(db, u)
    f = _folder(db, u, studio=st)
    create_board(db, u.id, BoardCreate(name="Root", studio_id=st.id))
    create_board(db, u.id, BoardCreate(name="InFolder", studio_id=st.id, folder_id=f.id))
    result = list_studio_boards(db, u.id, st.id)
    assert len(result.root_boards) == 1
    assert result.root_boards[0].name == "Root"
    assert len(result.folder_boards) == 1
    assert result.folder_boards[0].name == "InFolder"


def test_list_studio_boards_other_user_fails(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    with pytest.raises(ResourceNotFound):
        list_studio_boards(db, b.id, st.id)


# ======================================================================
# list_folder_boards
# ======================================================================


def test_list_folder_boards_returns_boards(db):
    u = _user(db)
    st = _studio(db, u)
    f = _folder(db, u, studio=st)
    create_board(db, u.id, BoardCreate(name="B1", studio_id=st.id, folder_id=f.id))
    create_board(db, u.id, BoardCreate(name="B2", studio_id=st.id, folder_id=f.id))
    result = list_folder_boards(db, u.id, f.id)
    assert len(result) == 2
    assert {r.name for r in result} == {"B1", "B2"}


def test_list_folder_boards_other_user_fails(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    f = _folder(db, a, studio=st)
    with pytest.raises(ResourceNotFound):
        list_folder_boards(db, b.id, f.id)


# ======================================================================
# create_board
# ======================================================================


def test_create_board_in_own_studio(db):
    u = _user(db)
    st = _studio(db, u)
    b = create_board(db, u.id, BoardCreate(name="Mi Board", studio_id=st.id))
    assert b.name == "Mi Board"
    assert b.id is not None
    assert b.version == 1


def test_created_board_persisted(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Persist", studio_id=st.id))
    db.expire_all()
    loaded = db.get(Board, created.id)
    assert loaded is not None
    assert loaded.name == "Persist"
    assert loaded.version == 1


def test_create_board_in_other_studio_fails(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    with pytest.raises(ResourceNotFound):
        create_board(db, b.id, BoardCreate(name="Hack", studio_id=st.id))


def test_create_board_without_folder_id(db):
    u = _user(db)
    st = _studio(db, u)
    b = create_board(db, u.id, BoardCreate(name="No Folder", studio_id=st.id))
    db.expire_all()
    loaded = db.get(Board, b.id)
    assert loaded.folder_id is None


def test_create_board_with_folder_same_studio(db):
    u = _user(db)
    st = _studio(db, u)
    f = _folder(db, u, studio=st)
    b = create_board(db, u.id, BoardCreate(name="In Folder", studio_id=st.id, folder_id=f.id))
    db.expire_all()
    loaded = db.get(Board, b.id)
    assert loaded.folder_id == f.id


def test_create_board_with_folder_other_studio_fails(db):
    u = _user(db)
    st_a = _studio(db, u, name="A")
    st_b = _studio(db, u, name="B")
    f = _folder(db, u, studio=st_b)
    with pytest.raises(ValidationFailure, match="carpeta no pertenece"):
        create_board(db, u.id, BoardCreate(name="Bad", studio_id=st_a.id, folder_id=f.id))


def test_create_board_with_other_user_folder_fails(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st_b = _studio(db, b)
    f_b = _folder(db, b, studio=st_b)
    with pytest.raises(ResourceNotFound):
        create_board(db, a.id, BoardCreate(name="Bad", studio_id=st_b.id, folder_id=f_b.id))


def test_create_board_default_values(db):
    u = _user(db)
    st = _studio(db, u)
    b = create_board(db, u.id, BoardCreate(studio_id=st.id))
    assert b.name == "Tablero sin nombre"


# ======================================================================
# get_board
# ======================================================================


def test_get_own_board(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Mi Board", studio_id=st.id))
    loaded = get_board(db, u.id, created.id)
    assert loaded.id == created.id
    assert loaded.name == "Mi Board"


def test_get_other_user_board_fails(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    b_created = create_board(db, a.id, BoardCreate(name="De A", studio_id=st.id))
    with pytest.raises(ResourceNotFound):
        get_board(db, b.id, b_created.id)


def test_get_nonexistent_board_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        get_board(db, u.id, "no-such-id")


def test_get_board_includes_nodes_and_edges(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Full", studio_id=st.id))
    board = db.get(Board, created.id)
    _node_inside(db, board, "n1")
    _node_inside(db, board, "n2")
    _edge_inside(db, board, "e1")
    db.expire_all()
    loaded = get_board(db, u.id, created.id)
    assert len(loaded.nodes) == 2
    assert len(loaded.edges) == 1
    assert loaded.edges[0].id == "e1"


# ======================================================================
# rename_board
# ======================================================================


def test_rename_own_board(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Original", studio_id=st.id))
    result = rename_board(db, u.id, created.id, BoardRename(name="Renombrado", expected_version=1))
    assert result.name == "Renombrado"
    db.expire_all()
    loaded = db.get(Board, created.id)
    assert loaded.name == "Renombrado"
    assert loaded.version == 2


def test_rename_other_user_board_fails(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    created = create_board(db, a.id, BoardCreate(name="De A", studio_id=st.id))
    with pytest.raises(ResourceNotFound):
        rename_board(db, b.id, created.id, BoardRename(name="Hackeado", expected_version=1))


def test_rename_nonexistent_board_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        rename_board(db, u.id, "no-such-id", BoardRename(name="Nope", expected_version=1))


def test_rename_updates_timestamp(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Before", studio_id=st.id))
    board_before = db.get(Board, created.id)
    original_updated = board_before.updated_at
    import time
    time.sleep(0.02)
    rename_board(db, u.id, created.id, BoardRename(name="After", expected_version=1))
    board_after = db.get(Board, created.id)
    assert board_after.updated_at > original_updated


def test_rename_does_not_change_other_fields(db):
    u = _user(db)
    st = _studio(db, u)
    f = _folder(db, u, studio=st)
    created = create_board(db, u.id, BoardCreate(name="Before", studio_id=st.id, folder_id=f.id))
    rename_board(db, u.id, created.id, BoardRename(name="Renamed", expected_version=1))
    db.expire_all()
    loaded = db.get(Board, created.id)
    assert loaded.studio_id == st.id
    assert loaded.folder_id == f.id


# ======================================================================
# delete_board
# ======================================================================


def test_delete_own_board(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="A borrar", studio_id=st.id))
    delete_board(db, u.id, created.id, expected_version=1)
    assert db.get(Board, created.id) is None


def test_delete_other_user_board_fails(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    created = create_board(db, a.id, BoardCreate(name="De A", studio_id=st.id))
    with pytest.raises(ResourceNotFound):
        delete_board(db, b.id, created.id, expected_version=1)
    assert db.get(Board, created.id) is not None


def test_delete_nonexistent_board_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        delete_board(db, u.id, "no-such-id", expected_version=1)


def test_delete_board_cascades_to_nodes_and_edges(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Cascade", studio_id=st.id))
    board = db.get(Board, created.id)
    _node_inside(db, board, "n1")
    _node_inside(db, board, "n2")
    _edge_inside(db, board, "e1")
    delete_board(db, u.id, created.id, expected_version=1)
    assert db.get(Board, created.id) is None
    assert db.get(Node, "n1") is None
    assert db.get(Node, "n2") is None
    assert db.get(Edge, "e1") is None


def test_delete_board_does_not_affect_other_boards(db):
    u = _user(db)
    st = _studio(db, u)
    b1 = create_board(db, u.id, BoardCreate(name="Keep", studio_id=st.id))
    b2 = create_board(db, u.id, BoardCreate(name="Delete", studio_id=st.id))
    board2 = db.get(Board, b2.id)
    _node_inside(db, board2, "n1")
    delete_board(db, u.id, b2.id, expected_version=1)
    assert db.get(Board, b1.id) is not None
    assert db.get(Board, b2.id) is None
    assert db.get(Node, "n1") is None


# ======================================================================
# board summary (via list_boards)
# ======================================================================


def test_list_board_summary_node_count(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Counts", studio_id=st.id))
    board = db.get(Board, created.id)
    _node_inside(db, board, "n1")
    _node_inside(db, board, "n2")
    result = list_boards(db, u.id)
    assert len(result) == 1
    assert result[0].node_count == 2
    assert result[0].edge_count == 0


def test_list_board_summary_edge_count(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Edges", studio_id=st.id))
    board = db.get(Board, created.id)
    _node_inside(db, board, "n1")
    _node_inside(db, board, "n2")
    _edge_inside(db, board, "e1")
    result = list_boards(db, u.id)
    assert result[0].node_count == 2
    assert result[0].edge_count == 1


def test_board_summary_excludes_other_user(db):
    a = _user(db, "a@test.com")
    b = _user(db, "b@test.com")
    st = _studio(db, a)
    create_board(db, a.id, BoardCreate(name="De A", studio_id=st.id))
    assert len(list_boards(db, b.id)) == 0


# ======================================================================
# board_state serialization
# ======================================================================


def test_board_state_with_ports_blocks_stages(db):
    """Verifica que board_state serializa correctamente datos complejos."""
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Complex", studio_id=st.id))

    # Agregar un nodo con ports, blocks y stages
    board = db.get(Board, created.id)
    n = Node(
        id="n1",
        board_id=board.id,
        type="card",
        title="Nodo complejo",
        ports=[{"id": "p1", "side": "left", "color": "#4ADE80", "label": "Entrada"}],
        blocks=[{"id": "b1", "type": "text", "value": "Hola"}],
        stages=[],
        tags=["importante"],
    )
    db.add(n)
    db.commit()

    state = get_board(db, u.id, created.id)
    assert len(state.nodes) == 1
    assert state.nodes[0].title == "Nodo complejo"
    assert state.nodes[0].tags == ["importante"]
    assert len(state.nodes[0].ports) == 1
    assert state.nodes[0].ports[0].color == "#4ADE80"
    assert len(state.nodes[0].blocks) == 1
    assert state.nodes[0].blocks[0].type == "text"


def test_board_state_with_timeline_stages(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Timeline", studio_id=st.id))
    board = db.get(Board, created.id)
    n = Node(
        id="t1",
        board_id=board.id,
        type="timeline",
        title="Línea",
        stages=[{"id": "s1", "title": "Paso 1", "tags": ["alpha"]}],
        ports=[], blocks=[], tags=[],
    )
    db.add(n)
    db.commit()

    state = get_board(db, u.id, created.id)
    assert len(state.nodes) == 1
    assert state.nodes[0].type == "timeline"
    assert len(state.nodes[0].stages) == 1
    assert state.nodes[0].stages[0].title == "Paso 1"


def test_board_state_with_image_block(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="Image", studio_id=st.id))
    board = db.get(Board, created.id)
    n = Node(
        id="img1",
        board_id=board.id,
        blocks=[{"id": "b1", "type": "image", "src": "data:image/png;base64,abc"}],
        ports=[], stages=[], tags=[],
    )
    db.add(n)
    db.commit()

    state = get_board(db, u.id, created.id)
    assert state.nodes[0].blocks[0].type == "image"
    assert state.nodes[0].blocks[0].src == "data:image/png;base64,abc"


# ======================================================================
# board_summary includes version
# ======================================================================


def test_board_summary_includes_version(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="V", studio_id=st.id))
    result = list_boards(db, u.id)
    assert result[0].version == 1


# ======================================================================
# VersionConflict tests
# ======================================================================


def test_rename_wrong_version_fails(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="B", studio_id=st.id))
    with pytest.raises(VersionConflict) as exc:
        rename_board(db, u.id, created.id, BoardRename(name="X", expected_version=99))
    assert exc.value.board_id == created.id
    assert exc.value.expected_version == 99
    assert exc.value.current_version == 1
    # Board name must NOT change
    db.expire_all()
    assert db.get(Board, created.id).name == "B"


def test_rename_conflict_does_not_change_timestamp(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="B", studio_id=st.id))
    before = db.get(Board, created.id).updated_at
    import time
    time.sleep(0.02)
    with pytest.raises(VersionConflict):
        rename_board(db, u.id, created.id, BoardRename(name="X", expected_version=99))
    db.expire_all()
    assert db.get(Board, created.id).updated_at == before


def test_delete_wrong_version_fails(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="B", studio_id=st.id))
    with pytest.raises(VersionConflict):
        delete_board(db, u.id, created.id, expected_version=99)
    # Board must still exist
    assert db.get(Board, created.id) is not None


def test_rename_increments_version_once(db):
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="B", studio_id=st.id))
    rename_board(db, u.id, created.id, BoardRename(name="X", expected_version=1))
    db.expire_all()
    assert db.get(Board, created.id).version == 2
    # Rename again
    rename_board(db, u.id, created.id, BoardRename(name="Y", expected_version=2))
    db.expire_all()
    assert db.get(Board, created.id).version == 3


def test_concurrent_rename_conflict(db):
    """Dos operaciones con la misma versión: primera funciona, segunda falla."""
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="B", studio_id=st.id))
    # Primera funciona
    rename_board(db, u.id, created.id, BoardRename(name="X", expected_version=1))
    # Segunda con versión obsoleta falla
    with pytest.raises(VersionConflict):
        rename_board(db, u.id, created.id, BoardRename(name="Y", expected_version=1))
    db.expire_all()
    board = db.get(Board, created.id)
    assert board.name == "X"
    assert board.version == 2


def test_rename_rollback_on_failure(db, monkeypatch):
    """Si rename falla después del incremento, la versión se revierte."""
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="B", studio_id=st.id))

    def _failing_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db, "commit", _failing_commit)
    with pytest.raises(RuntimeError):
        rename_board(db, u.id, created.id, BoardRename(name="X", expected_version=1))
    db.rollback()  # recuperar sesión
    db.expire_all()
    board = db.get(Board, created.id)
    assert board.name == "B"
    assert board.version == 1


def test_board_state_includes_version(db):
    """BoardState output incluye version."""
    u = _user(db)
    st = _studio(db, u)
    created = create_board(db, u.id, BoardCreate(name="B", studio_id=st.id))
    state = get_board(db, u.id, created.id)
    assert state.version == 1
