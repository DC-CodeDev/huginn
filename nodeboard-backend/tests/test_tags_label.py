"""Tests end-to-end de propagación de `tags` (Node) y `label` (Edge) — Fase 1 Paso 3.

Validan el contrato DB ↔ API llamando las funciones de ruta con una SQLite
temporal. Así se evita el bootstrap ASGI/lifespan del backend, que en este
entorno queda bloqueado, sin perder la semántica real de persistencia.
"""
import uuid

import pytest
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
    get_board,
    list_folder_boards,
    list_folders,
    list_studio_boards,
    list_studios,
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
    Port,
    PortRef,
    StudioCreate,
)
from app.services.errors import VersionConflict


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


_email_counter = 0


def _user(db) -> User:
    global _email_counter
    _email_counter += 1
    u = User(
        id=uuid.uuid4().hex[:16],
        email=f"test{_email_counter}@example.com",
        name="Test User",
        auth_provider="google",
    )
    db.add(u)
    db.commit()
    return u


def _studio(db, user=None, name="Studio", color="azul") -> str:
    u = user or _user(db)
    return create_studio(StudioCreate(name=name, color=color), db, current_user=u).id


def _board(db, user=None, studio_id=None) -> str:
    u = user or _user(db)
    sid = studio_id or _studio(db, user=u)
    return create_board(BoardCreate(name="B", studio_id=sid), db, current_user=u).id


def _folder(db, user=None, studio_id=None, name="Carpeta") -> str:
    u = user or _user(db)
    sid = studio_id or _studio(db, user=u)
    return create_folder(FolderCreate(name=name, studio_id=sid), db, current_user=u).id


def _make_node(node_id: str, **overrides) -> NodeSchema:
    return NodeSchema(
        id=node_id,
        title=overrides.pop("title", ""),
        tags=overrides.pop("tags", []),
        **overrides,
    )


def _node_create(node_id: str, expected_version: int = 1, **overrides) -> NodeCreateRequest:
    return NodeCreateRequest(
        **_make_node(node_id, **overrides).model_dump(),
        expected_version=expected_version,
    )


def _v(db, bid):
    """Helper: retorna la versión actual del board."""
    from app.models import Board as _B
    return db.get(_B, bid).version


def _board_with_edge(db, user=None, label="inicial", curved=True):
    """Crea board + dos nodos + una edge `e1`, y devuelve el board_id."""
    u = user or _user(db)
    bid = _board(db, user=u)
    v = _v(db, bid)  # version=1
    create_node(bid, _node_create("n1", expected_version=v), db, current_user=u)
    v = _v(db, bid)  # version=2
    create_node(bid, _node_create("n2", expected_version=v), db, current_user=u)
    v = _v(db, bid)  # version=3
    create_edge(
        bid,
        EdgeCreateRequest(
            id="e1",
            from_=PortRef(nodeId="n1", portId="p"),
            to=PortRef(nodeId="n2", portId="p"),
            curved=curved,
            label=label,
            expected_version=v,
        ),
        db,
        current_user=u,
    )
    return bid


def test_create_node_tags_roundtrip(db):
    u = _user(db)
    bid = _board(db, user=u)
    created = create_node(bid, _node_create("n1", tags=["alpha", "beta"]), db, current_user=u)
    assert created.tags == ["alpha", "beta"]
    # Se lee igual desde el estado completo del tablero
    node = get_board(bid, db, current_user=u).nodes[0]
    assert node.tags == ["alpha", "beta"]


def test_create_node_without_tags_defaults_empty(db):
    u = _user(db)
    bid = _board(db, user=u)
    created = create_node(bid, _node_create("n1"), db, current_user=u)
    assert created.tags == []


def test_create_edge_label_roundtrip(db):
    u = _user(db)
    bid = _board(db, user=u)
    v = _v(db, bid)
    create_node(bid, _node_create("n1", expected_version=v), db, current_user=u)
    v = _v(db, bid)
    create_node(bid, _node_create("n2", expected_version=v), db, current_user=u)
    v = _v(db, bid)
    created = create_edge(
        bid,
        EdgeCreateRequest(
            id="e1",
            from_=PortRef(nodeId="n1", portId="p"),
            to=PortRef(nodeId="n2", portId="p"),
            label="depende de",
            expected_version=v,
        ),
        db,
        current_user=u,
    )
    assert created.label == "depende de"
    assert get_board(bid, db, current_user=u).edges[0].label == "depende de"


def test_create_edge_without_label_defaults_empty(db):
    u = _user(db)
    bid = _board(db, user=u)
    v = _v(db, bid)
    create_node(bid, _node_create("n1", expected_version=v), db, current_user=u)
    v = _v(db, bid)
    create_node(bid, _node_create("n2", expected_version=v), db, current_user=u)
    v = _v(db, bid)
    created = create_edge(
        bid,
        EdgeCreateRequest(
            id="e1",
            from_=PortRef(nodeId="n1", portId="p"),
            to=PortRef(nodeId="n2", portId="p"),
            expected_version=v,
        ),
        db,
        current_user=u,
    )
    assert created.label == ""


def test_save_board_state_propagates_tags_and_label(db):
    u = _user(db)
    bid = _board(db, user=u)
    state = BoardStateSave(
        nodes=[
            _make_node("n1", title="Nodo", tags=["x", "y"]),
            _make_node("n2", title="Otro"),
        ],
        edges=[
            EdgeSchema(
                id="e1",
                from_=PortRef(nodeId="n1", portId="p"),
                to=PortRef(nodeId="n2", portId="p"),
                label="conecta",
            )
        ],
        expected_version=1,
    )
    save_board_state(bid, state, db, current_user=u)
    board = get_board(bid, db, current_user=u)
    nodes = {n.id: n for n in board.nodes}
    assert nodes["n1"].tags == ["x", "y"]
    assert nodes["n2"].tags == []       # sin tags -> default
    assert board.edges[0].label == "conecta"


def test_update_node_tags_absent_preserves(db):
    """PATCH sin la clave `tags` no debe pisar el valor existente."""
    u = _user(db)
    bid = _board(db, user=u)
    create_node(bid, _node_create("n1", expected_version=1, tags=["keep"]), db, current_user=u)
    update_node("n1", NodeUpdateRequest(title="nuevo", expected_version=2), db, current_user=u)
    node = get_board(bid, db, current_user=u).nodes[0]
    assert node.title == "nuevo"
    assert node.tags == ["keep"]


def test_update_node_tags_present_updates(db):
    u = _user(db)
    bid = _board(db, user=u)
    create_node(bid, _node_create("n1", expected_version=1, tags=["old"]), db, current_user=u)
    assert update_node("n1", NodeUpdateRequest(tags=["new1", "new2"], expected_version=2), db, current_user=u).tags == ["new1", "new2"]


def test_update_node_tags_null_clears(db):
    """`tags: null` explícito es distinto de ausente: limpia a lista vacía (no 500)."""
    u = _user(db)
    bid = _board(db, user=u)
    create_node(bid, _node_create("n1", expected_version=1, tags=["will", "clear"]), db, current_user=u)
    resp = update_node("n1", NodeUpdateRequest(tags=None, expected_version=2), db, current_user=u)
    assert resp.tags == []


def test_board_tags_aggregates_unique_sorted(db):
    """GET /tags une los tags de todos los nodos, deduplica y ordena case-insensitive."""
    u = _user(db)
    bid = _board(db, user=u)
    v = _v(db, bid)
    create_node(bid, _node_create("n1", expected_version=v, tags=["Beta", "alpha"]), db, current_user=u)
    v = _v(db, bid)
    create_node(bid, _node_create("n2", expected_version=v, tags=["alpha", "Zeta"]), db, current_user=u)
    assert board_tags(bid, db, current_user=u) == ["alpha", "Beta", "Zeta"]


def test_list_studios_filters_by_user(db):
    """Cada usuario solo ve sus propios studios."""
    a = _user(db)
    b = _user(db)
    _studio(db, user=a, name="Studio A")
    _studio(db, user=b, name="Studio B")

    a_studios = list_studios(db, current_user=a)
    b_studios = list_studios(db, current_user=b)
    assert len(a_studios) == 1
    assert a_studios[0].name == "Studio A"
    assert len(b_studios) == 1
    assert b_studios[0].name == "Studio B"


def test_delete_other_users_studio_returns_404(db):
    """Un usuario no puede eliminar un studio de otro (404)."""
    a = _user(db)
    b = _user(db)
    sid = _studio(db, user=a)
    from app.main import delete_studio
    import pytest
    with pytest.raises(Exception) as exc:
        delete_studio(sid, db, current_user=b)
    assert exc.typename == "HTTPException"
    # Confirmar que el studio sigue existiendo para el usuario A
    a_studios = list_studios(db, current_user=a)
    assert len(a_studios) == 1


# ======================================================================
# Board version in output
# ======================================================================


def test_board_state_includes_version(db):
    u = _user(db)
    bid = _board(db, user=u)
    state = get_board(bid, db, current_user=u)
    assert hasattr(state, "version")
    assert state.version == 1


def test_list_boards_includes_version(db):
    u = _user(db)
    _board(db, user=u)
    boards = list_studio_boards(
        _studio(db, user=u), db, current_user=u
    )
    for b in boards.root_boards:
        assert hasattr(b, "version")
