"""Tests unitarios del servicio de Edges.

Cubre: creación (válida/ajena/inexistente/nodos de otro board/serialización),
actualización (curved/label/parcial/ajena/inexistente),
eliminación (propia/ajena/inexistente/aislamiento),
board.updated_at, y optimistic locking.
"""
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Board, Edge, Node, Studio, User
from app.schemas import EdgeSchema, EdgeUpdate, PortRef
from app.services.edges import create_edge, create_edges_batch, delete_edge, update_edge
from app.services.errors import ResourceNotFound, ValidationFailure, VersionConflict


@pytest.fixture()
def engine():
    e = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        try:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass

    Base.metadata.create_all(bind=e)
    return e


@pytest.fixture()
def db(engine):
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
    b = Board(id=uuid.uuid4().hex[:16], name="B", studio_id=st.id, version=1)
    db.add(b)
    db.commit()
    return b


def _node(db, board, node_id="n1") -> Node:
    n = Node(id=node_id, board_id=board.id)
    db.add(n)
    db.commit()
    return n


def _edge_schema(edge_id="e1", from_n="n1", to_n="n2", **overrides) -> EdgeSchema:
    return EdgeSchema(
        id=edge_id,
        from_=PortRef(nodeId=from_n, portId="p"),
        to=PortRef(nodeId=to_n, portId="p"),
        **overrides,
    )


def _two_nodes(db, user=None, board=None):
    """Crea board + dos nodos, devuelve (board, n1_id, n2_id)."""
    u = user or _user(db)
    b = board or _board(db, u)
    _node(db, b, "n1")
    _node(db, b, "n2")
    return b, "n1", "n2"


# ======================================================================
# create_edge
# ======================================================================


def test_create_edge_valid(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    result = create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    assert result.id == "e1"
    assert result.label == ""
    assert result.curved is True


def test_create_edge_other_board_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    b, n1, n2 = _two_nodes(db, user=a)
    with pytest.raises(ResourceNotFound):
        create_edge(db, b_user.id, b.id, _edge_schema("e1"), expected_version=1)


def test_create_edge_nonexistent_board_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        create_edge(db, u.id, "no-such-board", _edge_schema("e1"), expected_version=1)


def test_create_edge_source_node_missing_fails(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n2")  # solo n2, falta n1
    with pytest.raises(ValidationFailure):
        create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)


def test_create_edge_target_node_missing_fails(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1")  # solo n1, falta n2
    with pytest.raises(ValidationFailure):
        create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)


def test_create_edge_source_from_other_board_fails(db):
    u = _user(db)
    b1, _, n2 = _two_nodes(db, user=u)  # n1, n2 en b1
    b2 = _board(db, u)
    _node(db, b2, "n3")  # n3 en b2
    # n1 está en b1, n3 está en b2 → edge en b1 no debe validar
    with pytest.raises(ValidationFailure):
        create_edge(db, u.id, b1.id, _edge_schema("e1", from_n="n1", to_n="n3"), expected_version=1)


def test_create_edge_target_from_other_board_fails(db):
    u = _user(db)
    b1, n1, _ = _two_nodes(db, user=u)  # n1 en b1
    b2 = _board(db, u)
    _node(db, b2, "n3")  # n3 en b2
    with pytest.raises(ValidationFailure):
        create_edge(db, u.id, b1.id, _edge_schema("e1", from_n="n1", to_n="n3"), expected_version=1)


def test_create_edge_conserves_from(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    result = create_edge(db, u.id, b.id, _edge_schema("e1", from_n="n1", to_n="n2"), expected_version=1)
    db.expire_all()
    edge = db.get(Edge, "e1")
    assert edge.from_node == "n1"
    assert edge.from_port == "p"


def test_create_edge_conserves_to(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    result = create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    assert result.to.nodeId == "n2"
    assert result.to.portId == "p"


def test_create_edge_conserves_curved(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    result = create_edge(db, u.id, b.id, _edge_schema("e1", curved=False), expected_version=1)
    assert result.curved is False


def test_create_edge_conserves_label(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    result = create_edge(db, u.id, b.id, _edge_schema("e1", label="depende de"), expected_version=1)
    assert result.label == "depende de"


def test_create_edge_generates_id(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    result = create_edge(db, u.id, b.id, _edge_schema(None), expected_version=1)
    assert result.id is not None
    assert len(result.id) == 32


def test_create_edge_updates_board_timestamp(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    orig_updated = b.updated_at
    import time
    time.sleep(0.02)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).updated_at > orig_updated


def test_create_edge_persists(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    db.expire_all()
    assert db.get(Edge, "e1") is not None


# ======================================================================
# update_edge
# ======================================================================


def test_update_curved(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1", curved=True), expected_version=1)
    result = update_edge(db, u.id, "e1", EdgeUpdate(curved=False), expected_version=2)
    assert result.curved is False


def test_update_label(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1", label="old"), expected_version=1)
    result = update_edge(db, u.id, "e1", EdgeUpdate(label="new"), expected_version=2)
    assert result.label == "new"


def test_update_label_null(db):
    """Label explícitamente null debe convertirse a vacío."""
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1", label="text"), expected_version=1)
    result = update_edge(db, u.id, "e1", EdgeUpdate(label=None), expected_version=2)
    assert result.label == ""


def test_update_preserves_unset_fields(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1", curved=False, label="keep"), expected_version=1)
    result = update_edge(db, u.id, "e1", EdgeUpdate(curved=True), expected_version=2)
    assert result.curved is True
    assert result.label == "keep"  # no enviado


def test_update_other_user_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    ba, n1, n2 = _two_nodes(db, user=a)
    create_edge(db, a.id, ba.id, _edge_schema("e1"), expected_version=1)
    with pytest.raises(ResourceNotFound):
        update_edge(db, b_user.id, "e1", EdgeUpdate(label="Hack"), expected_version=1)


def test_update_nonexistent_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        update_edge(db, u.id, "no-such-edge", EdgeUpdate(label="Nope"), expected_version=1)


def test_update_board_timestamp(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    import time
    time.sleep(0.02)
    db.expire_all()
    orig_updated = db.get(Board, b.id).updated_at
    update_edge(db, u.id, "e1", EdgeUpdate(label="x"), expected_version=2)
    db.expire_all()
    assert db.get(Board, b.id).updated_at > orig_updated


# ======================================================================
# delete_edge
# ======================================================================


def test_delete_own_edge(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    delete_edge(db, u.id, "e1", expected_version=2)
    assert db.get(Edge, "e1") is None


def test_delete_other_user_edge_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    ba, n1, n2 = _two_nodes(db, user=a)
    create_edge(db, a.id, ba.id, _edge_schema("e1"), expected_version=1)
    with pytest.raises(ResourceNotFound):
        delete_edge(db, b_user.id, "e1", expected_version=1)
    assert db.get(Edge, "e1") is not None


def test_delete_nonexistent_edge_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        delete_edge(db, u.id, "no-such-id", expected_version=1)


def test_delete_does_not_affect_other_edges(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    _node(db, b, "n3")
    create_edge(db, u.id, b.id, _edge_schema("e1", from_n="n1", to_n="n2"), expected_version=1)
    create_edge(db, u.id, b.id, _edge_schema("e2", from_n="n1", to_n="n3"), expected_version=2)
    delete_edge(db, u.id, "e1", expected_version=3)
    assert db.get(Edge, "e1") is None
    assert db.get(Edge, "e2") is not None


def test_delete_does_not_affect_nodes(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    delete_edge(db, u.id, "e1", expected_version=2)
    assert db.get(Node, "n1") is not None
    assert db.get(Node, "n2") is not None


def test_delete_persists(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    delete_edge(db, u.id, "e1", expected_version=2)
    db.expire_all()
    assert db.get(Edge, "e1") is None


# ======================================================================
# optimistic locking — versioning
# ======================================================================


def test_create_edge_increments_version(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_update_edge_increments_version(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    update_edge(db, u.id, "e1", EdgeUpdate(label="x"), expected_version=2)
    db.expire_all()
    assert db.get(Board, b.id).version == 3


def test_delete_edge_increments_version(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    delete_edge(db, u.id, "e1", expected_version=2)
    db.expire_all()
    assert db.get(Board, b.id).version == 3


def test_create_edge_wrong_version_fails(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    with pytest.raises(VersionConflict):
        create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=99)
    assert db.get(Edge, "e1") is None


def test_update_edge_wrong_version_fails(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1", label="x"), expected_version=1)
    with pytest.raises(VersionConflict):
        update_edge(db, u.id, "e1", EdgeUpdate(label="y"), expected_version=99)
    db.expire_all()
    assert db.get(Edge, "e1").label == "x"


def test_delete_edge_wrong_version_fails(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    with pytest.raises(VersionConflict):
        delete_edge(db, u.id, "e1", expected_version=99)
    assert db.get(Edge, "e1") is not None


def test_edge_ops_increment_exactly_one(db):
    """Cada operación de edge incrementa exactamente 1."""
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_create_edge_rollback_reverts_version(db, monkeypatch):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)

    def _failing_commit():
        raise RuntimeError("boom")

    monkeypatch.setattr(db, "commit", _failing_commit)
    with pytest.raises(RuntimeError):
        create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    db.rollback()
    db.expire_all()
    assert db.get(Board, b.id).version == 1
    assert db.get(Edge, "e1") is None


def test_concurrent_create_edge_conflict(db):
    """Dos creates con misma versión: primero funciona, segundo falla."""
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    with pytest.raises(VersionConflict):
        create_edge(db, u.id, b.id, _edge_schema("e2"), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).version == 2


# ======================================================================
# port validation
# ======================================================================


def test_create_edge_valid_port_source(db):
    """Puerto origen existente es válido."""
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1")
    _node(db, b, "n2")
    n1 = db.get(Node, "n1")
    n1.ports = [{"id": "p", "side": "left", "color": "#4ADE80", "label": "in"}]
    db.commit()
    result = create_edge(
        db, u.id, b.id,
        _edge_schema("e1", from_n="n1", to_n="n2"),
        expected_version=1,
    )
    assert result.id == "e1"


def test_create_edge_invalid_port_source_fails(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1")
    _node(db, b, "n2")
    n1 = db.get(Node, "n1")
    n1.ports = [{"id": "p1", "side": "left", "color": "#4ADE80", "label": "in"}]
    db.commit()
    with pytest.raises(ValidationFailure, match="Puerto origen"):
        create_edge(
            db, u.id, b.id,
            _edge_schema("e1", from_n="n1", to_n="n2"),
            expected_version=1,
        )


def test_create_edge_invalid_port_target_fails(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1")
    _node(db, b, "n2")
    n2 = db.get(Node, "n2")
    n2.ports = [{"id": "p2", "side": "right", "color": "#60A5FA", "label": "out"}]
    db.commit()
    with pytest.raises(ValidationFailure, match="Puerto destino"):
        create_edge(
            db, u.id, b.id,
            _edge_schema("e1", from_n="n1", to_n="n2"),
            expected_version=1,
        )


def test_create_edge_both_ports_valid(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1")
    _node(db, b, "n2")
    n1 = db.get(Node, "n1")
    n1.ports = [{"id": "p", "side": "left", "color": "#4ADE80", "label": "in"}]
    n2 = db.get(Node, "n2")
    n2.ports = [{"id": "p", "side": "right", "color": "#60A5FA", "label": "out"}]
    db.commit()
    result = create_edge(
        db, u.id, b.id,
        _edge_schema("e1", from_n="n1", to_n="n2"),
        expected_version=1,
    )
    assert result.id == "e1"


def test_create_edge_preloaded_board(db):
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    board_obj = db.get(Board, b.id)
    result = create_edge(
        db, u.id, b.id, _edge_schema("e1"), expected_version=1,
        board=board_obj,
    )
    assert result.id == "e1"
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_create_edge_no_ports_on_nodes_skips_validation(db):
    """Si los nodos no tienen puertos, la validación se salta."""
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    result = create_edge(
        db, u.id, b.id, _edge_schema("e1"), expected_version=1,
    )
    assert result.id == "e1"


def test_create_edge_self_edge_allowed(db):
    """El dominio permite conectar un nodo consigo mismo."""
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1")
    result = create_edge(
        db, u.id, b.id,
        _edge_schema("e1", from_n="n1", to_n="n1"),
        expected_version=1,
    )
    assert result.id == "e1"
    assert result.from_.nodeId == "n1"
    assert result.to.nodeId == "n1"


def test_create_edge_duplicates_allowed(db):
    """El dominio permite múltiples edges idénticos."""
    u = _user(db)
    b, n1, n2 = _two_nodes(db, user=u)
    create_edge(db, u.id, b.id, _edge_schema("e1"), expected_version=1)
    result = create_edge(db, u.id, b.id, _edge_schema("e2"), expected_version=2)
    assert result.id == "e2"
    db.expire_all()
    count = db.query(Edge).filter(
        Edge.from_node == "n1", Edge.to_node == "n2"
    ).count()
    assert count == 2


def test_create_edge_concurrent_two_sessions(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup = TestingSession()
    try:
        u = _user(setup)
        user_id = u.id
        b = _board(setup, u)
        board_id = b.id
        _node(setup, b, "n1")
        _node(setup, b, "n2")
    finally:
        setup.close()

    db_a = TestingSession()
    db_b = TestingSession()
    try:
        create_edge(db_a, user_id, board_id, _edge_schema("e1"), expected_version=1)
        with pytest.raises(VersionConflict) as exc:
            create_edge(db_b, user_id, board_id, _edge_schema("e2"), expected_version=1)
        assert exc.value.expected_version == 1
        assert exc.value.current_version == 2

        verify = TestingSession()
        try:
            edges = verify.query(Edge).filter(Edge.board_id == board_id).all()
            board = verify.get(Board, board_id)
            assert len(edges) == 1
            assert edges[0].id == "e1"
            assert board.version == 2
        finally:
            verify.close()
    finally:
        db_a.close()
        db_b.close()


# ======================================================================
# create_edges_batch
# ======================================================================


def _two_nodes_in(db, board, n1_id="n1", n2_id="n2"):
    """Crea dos nodos en *board* y devuelve sus IDs."""
    _node(db, board, n1_id)
    _node(db, board, n2_id)
    return n1_id, n2_id


def _batch_edge_schemas(from_n="n1", to_n="n2", count=1, **overrides) -> list[EdgeSchema]:
    return [
        EdgeSchema(
            id=None,
            from_=PortRef(nodeId=from_n, portId="p"),
            to=PortRef(nodeId=to_n, portId="p"),
            label=f"edge-{i}",
            **overrides,
        )
        for i in range(count)
    ]


def test_create_edges_batch_single(db):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)
    result = create_edges_batch(db, u.id, b.id, _batch_edge_schemas(count=1), expected_version=1)
    assert len(result["edges"]) == 1
    assert result["edges"][0].label == "edge-0"
    assert result["client_map"] == {0: result["edges"][0].id}
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_create_edges_batch_multiple(db):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)
    payloads = _batch_edge_schemas(count=3)
    result = create_edges_batch(db, u.id, b.id, payloads, expected_version=1)
    assert len(result["edges"]) == 3
    assert [e.label for e in result["edges"]] == ["edge-0", "edge-1", "edge-2"]
    assert len(result["client_map"]) == 3


def test_create_edges_batch_preserves_order(db):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)
    payloads = [
        EdgeSchema(id=None, from_=PortRef(nodeId="n1", portId="p"), to=PortRef(nodeId="n2", portId="p"), label="Z"),
        EdgeSchema(id=None, from_=PortRef(nodeId="n1", portId="p"), to=PortRef(nodeId="n2", portId="p"), label="A"),
        EdgeSchema(id=None, from_=PortRef(nodeId="n1", portId="p"), to=PortRef(nodeId="n2", portId="p"), label="M"),
    ]
    result = create_edges_batch(db, u.id, b.id, payloads, expected_version=1)
    assert [e.label for e in result["edges"]] == ["Z", "A", "M"]


def test_create_edges_batch_generates_ids(db):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)
    result = create_edges_batch(db, u.id, b.id, _batch_edge_schemas(count=2), expected_version=1)
    for e in result["edges"]:
        assert e.id is not None
        assert len(e.id) == 32
    assert result["edges"][0].id != result["edges"][1].id


def test_create_edges_batch_increments_version_once(db):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)
    create_edges_batch(db, u.id, b.id, _batch_edge_schemas(count=5), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_create_edges_batch_updates_timestamp(db):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)
    orig = b.updated_at
    import time
    time.sleep(0.02)
    create_edges_batch(db, u.id, b.id, _batch_edge_schemas(count=1), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).updated_at > orig


def test_create_edges_batch_preloaded_board(db):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)
    board_obj = db.get(Board, b.id)
    result = create_edges_batch(
        db, u.id, b.id, _batch_edge_schemas(count=1), expected_version=1, board=board_obj,
    )
    assert result["edges"][0].label == "edge-0"


def test_create_edges_batch_wrong_version_fails(db):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)
    with pytest.raises(VersionConflict):
        create_edges_batch(db, u.id, b.id, _batch_edge_schemas(count=1), expected_version=99)
    db.expire_all()
    assert db.get(Board, b.id).version == 1


def test_create_edges_batch_source_node_missing_fails(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n2")  # solo n2
    with pytest.raises(ValidationFailure):
        create_edges_batch(db, u.id, b.id, _batch_edge_schemas(from_n="n1", to_n="n2", count=1), expected_version=1)


def test_create_edges_batch_target_node_missing_fails(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1")  # solo n1
    with pytest.raises(ValidationFailure):
        create_edges_batch(db, u.id, b.id, _batch_edge_schemas(from_n="n1", to_n="n2", count=1), expected_version=1)


def test_create_edges_batch_node_from_other_board_fails(db):
    u = _user(db)
    b1, _, _ = _two_nodes(db, user=u)
    b2 = _board(db, u)
    _node(db, b2, "n3")
    # n1 está en b1, n3 en b2 → edge en b1 con destino n3 falla
    with pytest.raises(ValidationFailure):
        payloads = [
            EdgeSchema(id=None, from_=PortRef(nodeId="n1", portId="p"), to=PortRef(nodeId="n3", portId="p")),
        ]
        create_edges_batch(db, u.id, b1.id, payloads, expected_version=1)


def test_create_edges_batch_other_board_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    ba, _, _ = _two_nodes(db, user=a)
    with pytest.raises(ResourceNotFound):
        create_edges_batch(db, b_user.id, ba.id, _batch_edge_schemas(count=1), expected_version=1)


def test_create_edges_batch_nonexistent_board_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        create_edges_batch(db, u.id, "no-such-board", _batch_edge_schemas(count=1), expected_version=1)


def test_create_edges_batch_valid_ports(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1")
    _node(db, b, "n2")
    n1 = db.get(Node, "n1")
    n1.ports = [{"id": "out", "side": "right", "color": "#60A5FA", "label": ""}]
    n2 = db.get(Node, "n2")
    n2.ports = [{"id": "in", "side": "left", "color": "#4ADE80", "label": ""}]
    db.commit()
    payloads = [
        EdgeSchema(id=None, from_=PortRef(nodeId="n1", portId="out"), to=PortRef(nodeId="n2", portId="in")),
    ]
    result = create_edges_batch(db, u.id, b.id, payloads, expected_version=1)
    assert len(result["edges"]) == 1


def test_create_edges_batch_invalid_port_fails(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1")
    _node(db, b, "n2")
    n1 = db.get(Node, "n1")
    n1.ports = [{"id": "p1", "side": "left", "color": "#4ADE80", "label": "in"}]
    db.commit()
    with pytest.raises(ValidationFailure):
        payloads = [
            EdgeSchema(id=None, from_=PortRef(nodeId="n1", portId="nonexistent"), to=PortRef(nodeId="n2", portId="p")),
        ]
        create_edges_batch(db, u.id, b.id, payloads, expected_version=1)


def test_create_edges_batch_self_edge(db):
    u = _user(db)
    b = _board(db, u)
    _node(db, b, "n1")
    payloads = [
        EdgeSchema(id=None, from_=PortRef(nodeId="n1", portId="p"), to=PortRef(nodeId="n1", portId="p")),
    ]
    result = create_edges_batch(db, u.id, b.id, payloads, expected_version=1)
    assert len(result["edges"]) == 1
    assert result["edges"][0].from_.nodeId == "n1"
    assert result["edges"][0].to.nodeId == "n1"


def test_create_edges_batch_duplicates_allowed(db):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)
    payloads = _batch_edge_schemas(count=2)
    result = create_edges_batch(db, u.id, b.id, payloads, expected_version=1)
    assert len(result["edges"]) == 2


def test_create_edges_batch_rollback_mid_batch(db, monkeypatch):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)

    def _failing_commit():
        raise RuntimeError("mid-batch boom")

    monkeypatch.setattr(db, "commit", _failing_commit)
    with pytest.raises(RuntimeError):
        create_edges_batch(db, u.id, b.id, _batch_edge_schemas(count=2), expected_version=1)
    db.rollback()
    db.expire_all()
    assert db.get(Board, b.id).version == 1
    assert db.query(Edge).filter(Edge.board_id == b.id).count() == 0


def test_create_edges_batch_preserves_existing(db):
    u = _user(db)
    b = _board(db, u)
    _two_nodes_in(db, b)
    create_edge(db, u.id, b.id, _edge_schema("existing"), expected_version=1)
    result = create_edges_batch(db, u.id, b.id, _batch_edge_schemas(count=1), expected_version=2)
    db.expire_all()
    assert db.get(Edge, "existing") is not None
    assert len(result["edges"]) == 1


def test_create_edges_batch_concurrent_conflict(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup = TestingSession()
    try:
        u = _user(setup)
        user_id = u.id
        b = _board(setup, u)
        board_id = b.id
        _node(setup, b, "n1")
        _node(setup, b, "n2")
    finally:
        setup.close()

    db_a = TestingSession()
    db_b = TestingSession()
    try:
        p1 = [EdgeSchema(id=None, from_=PortRef(nodeId="n1", portId="p"), to=PortRef(nodeId="n2", portId="p"), label="Ganador")]
        p2 = [EdgeSchema(id=None, from_=PortRef(nodeId="n1", portId="p"), to=PortRef(nodeId="n2", portId="p"), label="Perdedor")]
        result_a = create_edges_batch(db_a, user_id, board_id, p1, expected_version=1)
        assert len(result_a["edges"]) == 1
        with pytest.raises(VersionConflict) as exc:
            create_edges_batch(db_b, user_id, board_id, p2, expected_version=1)
        assert exc.value.expected_version == 1
        assert exc.value.current_version == 2

        verify = TestingSession()
        try:
            edges = verify.query(Edge).filter(Edge.board_id == board_id).all()
            board = verify.get(Board, board_id)
            assert len(edges) == 1
            assert edges[0].label == "Ganador"
            assert board.version == 2
        finally:
            verify.close()
    finally:
        db_a.close()
        db_b.close()
