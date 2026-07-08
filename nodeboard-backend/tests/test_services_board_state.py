"""Tests unitarios del servicio de guardado de estado de Board (snapshot).

Cubre: carga de estado, reemplazo básico, tipos de node, edges,
validaciones (duplicados, referencias), atomicidad (rollback),
aislamiento entre usuarios/boards, y optimistic locking.
"""
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Board, Edge, Node, Studio, User
from app.schemas import (
    BoardStateSave,
    EdgeSchema,
    NodeSchema,
    PortRef,
)
from app.services.board_state import load_board_state, save_board_state
from app.services.errors import ResourceNotFound, ValidationFailure, VersionConflict


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
    b = Board(id=uuid.uuid4().hex[:16], name="B", studio_id=st.id, version=1)
    db.add(b)
    db.commit()
    return b


def _make_node(node_id, **overrides) -> NodeSchema:
    return NodeSchema(id=node_id, **overrides)


def _make_edge(edge_id, from_n="n1", to_n="n2", **overrides) -> EdgeSchema:
    return EdgeSchema(
        id=edge_id,
        from_=PortRef(nodeId=from_n, portId="p"),
        to=PortRef(nodeId=to_n, portId="p"),
        **overrides,
    )


# ======================================================================
# load_board_state
# ======================================================================


def test_load_own_board(db):
    u = _user(db)
    b = _board(db, u)
    state = load_board_state(db, u.id, b.id)
    assert state.id == b.id
    assert state.name == "B"


def test_load_other_board_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    b = _board(db, a)
    with pytest.raises(ResourceNotFound):
        load_board_state(db, b_user.id, b.id)


def test_load_nonexistent_board_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        load_board_state(db, u.id, "no-such-id")


def test_load_does_not_commit(db):
    u = _user(db)
    b = _board(db, u)
    load_board_state(db, u.id, b.id)
    db.rollback()
    assert load_board_state(db, u.id, b.id).id == b.id


def test_load_contains_nodes_and_edges(db):
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="n1", board_id=b.id))
    db.add(Edge(id="e1", board_id=b.id, from_node="n1", from_port="p", to_node="n2", to_port="p"))
    db.commit()
    state = load_board_state(db, u.id, b.id)
    assert len(state.nodes) == 1
    assert len(state.edges) == 1


# ======================================================================
# save_board_state — reemplazo básico
# ======================================================================


def test_save_empty_to_nodes(db):
    u = _user(db)
    b = _board(db, u)
    payload = BoardStateSave(nodes=[], edges=[], expected_version=1)
    result = save_board_state(db, u.id, b.id, payload)
    assert len(result.nodes) == 0
    assert len(result.edges) == 0


def test_save_replaces_existing_content(db):
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="old", board_id=b.id))
    db.commit()
    payload = BoardStateSave(
        nodes=[_make_node("n1")],
        edges=[],
        expected_version=1,
    )
    result = save_board_state(db, u.id, b.id, payload)
    assert len(result.nodes) == 1
    assert result.nodes[0].id == "n1"
    assert db.get(Node, "old") is None


def test_save_removes_omitted_nodes(db):
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="n1", board_id=b.id))
    db.add(Node(id="n2", board_id=b.id))
    db.commit()
    result = save_board_state(db, u.id, b.id, BoardStateSave(nodes=[_make_node("n1")], edges=[], expected_version=1))
    assert len(result.nodes) == 1
    assert db.get(Node, "n2") is None


def test_save_removes_omitted_edges(db):
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="n1", board_id=b.id))
    db.add(Node(id="n2", board_id=b.id))
    db.add(Edge(id="e1", board_id=b.id, from_node="n1", from_port="p", to_node="n2", to_port="p"))
    db.commit()
    result = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1"), _make_node("n2")],
        edges=[],
        expected_version=1,
    ))
    assert len(result.edges) == 0
    assert db.get(Edge, "e1") is None


def test_save_conserves_ids(db):
    u = _user(db)
    b = _board(db, u)
    result = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("custom-id")],
        edges=[],
        expected_version=1,
    ))
    assert result.nodes[0].id == "custom-id"


def test_save_updates_timestamp(db):
    u = _user(db)
    b = _board(db, u)
    import time
    time.sleep(0.02)
    before = load_board_state(db, u.id, b.id).updated_at
    save_board_state(db, u.id, b.id, BoardStateSave(nodes=[], edges=[], expected_version=1))
    after = load_board_state(db, u.id, b.id).updated_at
    assert after > before


def test_save_returns_full_state(db):
    u = _user(db)
    b = _board(db, u)
    result = save_board_state(
        db, u.id, b.id,
        BoardStateSave(nodes=[_make_node("n1", title="T")], edges=[], expected_version=1),
    )
    assert result.id == b.id
    assert len(result.nodes) == 1


# ======================================================================
# tipos de node
# ======================================================================


def test_save_card_node(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1", type="card", title="Card", x=10, y=20, w=300)],
        edges=[],
        expected_version=1,
    ))
    assert r.nodes[0].type == "card"
    assert r.nodes[0].x == 10
    assert r.nodes[0].y == 20
    assert r.nodes[0].w == 300


def test_save_timeline_node(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("t1", type="timeline", title="TL")],
        edges=[],
        expected_version=1,
    ))
    assert r.nodes[0].type == "timeline"


def test_save_conserves_blocks(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1", blocks=[{"id": "b1", "type": "text", "value": "hello"}])],
        edges=[],
        expected_version=1,
    ))
    assert r.nodes[0].blocks[0].value == "hello"


def test_save_conserves_image_block(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1", blocks=[{"id": "b1", "type": "image", "src": "data:img/png;x"}])],
        edges=[],
        expected_version=1,
    ))
    assert r.nodes[0].blocks[0].src == "data:img/png;x"


def test_save_conserves_stages(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("t1", type="timeline", stages=[{"id": "s1", "title": "P", "tags": ["x"]}])],
        edges=[],
        expected_version=1,
    ))
    assert r.nodes[0].stages[0].title == "P"


def test_save_conserves_ports(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1", ports=[{"id": "p1", "side": "left", "color": "#4ADE80", "label": "IN"}])],
        edges=[],
        expected_version=1,
    ))
    assert r.nodes[0].ports[0].label == "IN"


def test_save_conserves_tags(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1", tags=["alpha", "beta"])],
        edges=[],
        expected_version=1,
    ))
    assert r.nodes[0].tags == ["alpha", "beta"]


# ======================================================================
# edges
# ======================================================================


def test_save_edge_valid(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1"), _make_node("n2")],
        edges=[_make_edge("e1")],
        expected_version=1,
    ))
    assert len(r.edges) == 1
    assert r.edges[0].id == "e1"


def test_save_edge_conserves_source(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1"), _make_node("n2")],
        edges=[_make_edge("e1")],
        expected_version=1,
    ))
    assert r.edges[0].from_.nodeId == "n1"
    assert r.edges[0].from_.portId == "p"


def test_save_edge_conserves_target(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1"), _make_node("n2")],
        edges=[_make_edge("e1")],
        expected_version=1,
    ))
    assert r.edges[0].to.nodeId == "n2"


def test_save_edge_conserves_curved(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1"), _make_node("n2")],
        edges=[_make_edge("e1", curved=False)],
        expected_version=1,
    ))
    assert r.edges[0].curved is False


def test_save_edge_conserves_label(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1"), _make_node("n2")],
        edges=[_make_edge("e1", label="depende")],
        expected_version=1,
    ))
    assert r.edges[0].label == "depende"


def test_save_multiple_edges(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1"), _make_node("n2"), _make_node("n3")],
        edges=[_make_edge("e1", from_n="n1", to_n="n2"), _make_edge("e2", from_n="n2", to_n="n3")],
        expected_version=1,
    ))
    assert len(r.edges) == 2


# ======================================================================
# validaciones
# ======================================================================


def test_duplicate_node_id_fails(db):
    u = _user(db)
    b = _board(db, u)
    with pytest.raises(ValidationFailure, match="duplicado"):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1"), _make_node("n1")],
            edges=[],
            expected_version=1,
        ))


def test_duplicate_edge_id_fails(db):
    u = _user(db)
    b = _board(db, u)
    with pytest.raises(ValidationFailure, match="duplicado"):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1"), _make_node("n2")],
            edges=[_make_edge("e1"), _make_edge("e1")],
            expected_version=1,
        ))


def test_edge_source_not_in_snapshot_fails(db):
    u = _user(db)
    b = _board(db, u)
    with pytest.raises(ValidationFailure, match="origen"):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n2")],  # falta n1
            edges=[_make_edge("e1", from_n="n1", to_n="n2")],
            expected_version=1,
        ))


def test_edge_target_not_in_snapshot_fails(db):
    u = _user(db)
    b = _board(db, u)
    with pytest.raises(ValidationFailure, match="destino"):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1")],  # falta n2
            edges=[_make_edge("e1", from_n="n1", to_n="n2")],
            expected_version=1,
        ))


def test_invalid_payload_does_not_modify_board(db):
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="keep", board_id=b.id))
    db.commit()
    with pytest.raises(ValidationFailure):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1"), _make_node("n1")],  # duplicado
            edges=[],
            expected_version=1,
        ))
    assert db.get(Node, "keep") is not None


def test_other_user_board_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    b = _board(db, a)
    with pytest.raises(ResourceNotFound):
        save_board_state(db, b_user.id, b.id, BoardStateSave(nodes=[], edges=[], expected_version=1))


def test_nonexistent_board_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        save_board_state(db, u.id, "no-such-id", BoardStateSave(nodes=[], edges=[], expected_version=1))


# ======================================================================
# atomicidad y rollback
# ======================================================================


def test_edge_validation_rollbacks_node_insertion(db):
    """Si una edge es inválida, los nodes del snapshot no deben persistir."""
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="original", board_id=b.id))
    db.commit()
    with pytest.raises(ValidationFailure):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1"), _make_node("n2")],
            edges=[_make_edge("e1", from_n="n1", to_n="missing")],
            expected_version=1,
        ))
    # El board debe conservar el estado original
    assert db.get(Node, "original") is not None
    assert db.get(Node, "n1") is None


def test_rollback_leaves_original_state_intact(db):
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="n1", board_id=b.id))
    db.add(Node(id="n2", board_id=b.id))
    db.add(Edge(id="e1", board_id=b.id, from_node="n1", from_port="p", to_node="n2", to_port="p"))
    db.commit()
    with pytest.raises(ValidationFailure):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1"), _make_node("n1")],  # duplicado
            edges=[],
            expected_version=1,
        ))
    # Estado original intacto
    assert db.get(Node, "n2") is not None
    assert db.get(Edge, "e1") is not None


def test_timestamp_not_updated_on_rollback(db):
    u = _user(db)
    b = _board(db, u)
    before = load_board_state(db, u.id, b.id).updated_at
    with pytest.raises(ValidationFailure):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1"), _make_node("n1")],
            edges=[],
            expected_version=1,
        ))
    after = load_board_state(db, u.id, b.id).updated_at
    assert after == before


# ======================================================================
# aislamiento
# ======================================================================


def test_save_one_board_does_not_affect_another(db):
    u = _user(db)
    b1 = _board(db, u)
    b2 = _board(db, u)
    db.add(Node(id="b2-node", board_id=b2.id))
    db.commit()
    save_board_state(db, u.id, b1.id, BoardStateSave(
        nodes=[_make_node("b1-node")],
        edges=[],
        expected_version=1,
    ))
    assert db.get(Node, "b1-node") is not None
    assert db.get(Node, "b2-node") is not None


def test_save_user_a_does_not_affect_user_b(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    ba = _board(db, a)
    bb = _board(db, b_user)
    db.add(Node(id="b-node", board_id=bb.id))
    db.commit()
    save_board_state(db, a.id, ba.id, BoardStateSave(
        nodes=[_make_node("a-node")],
        edges=[],
        expected_version=1,
    ))
    assert db.get(Node, "a-node") is not None
    assert db.get(Node, "b-node") is not None


def test_edge_in_snapshot_must_reference_same_snapshot_nodes(db):
    """No se puede crear edge hacia un node que existía antes pero no está en el snapshot."""
    u = _user(db)
    b = _board(db, u)
    Node(id="n1", board_id=b.id)
    Node(id="n2", board_id=b.id)
    db.commit()
    with pytest.raises(ValidationFailure):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1")],  # solo n1, falta n2 en el snapshot
            edges=[_make_edge("e1", from_n="n1", to_n="n2")],
            expected_version=1,
        ))


# ======================================================================
# rollback explícito en fallos de flush/commit
# ======================================================================


def test_flush_failure_triggers_rollback(db, monkeypatch):
    u = _user(db)
    b = _board(db, u)

    def _failing_flush():
        raise RuntimeError("flush explosion")

    monkeypatch.setattr(db, "flush", _failing_flush)
    orig_rollback = db.rollback
    rollback_called = False

    def _track_rollback():
        nonlocal rollback_called
        rollback_called = True
        return orig_rollback()

    monkeypatch.setattr(db, "rollback", _track_rollback)

    with pytest.raises(RuntimeError, match="flush explosion"):
        save_board_state(db, u.id, b.id, BoardStateSave(nodes=[_make_node("n1")], edges=[], expected_version=1))

    assert rollback_called, "rollback() debe llamarse tras fallo de flush()"
    # La sesión debe seguir usable
    assert db.get(Board, b.id) is not None


def test_commit_failure_triggers_rollback(db, monkeypatch):
    u = _user(db)
    b = _board(db, u)

    def _failing_commit():
        raise RuntimeError("commit explosion")

    monkeypatch.setattr(db, "commit", _failing_commit)
    rollback_called = False
    orig_rollback = db.rollback

    def _track_rollback():
        nonlocal rollback_called
        rollback_called = True
        return orig_rollback()

    monkeypatch.setattr(db, "rollback", _track_rollback)
    refresh_called = False
    orig_refresh = db.refresh

    def _track_refresh(*args, **kwargs):
        nonlocal refresh_called
        refresh_called = True
        return orig_refresh(*args, **kwargs)

    monkeypatch.setattr(db, "refresh", _track_refresh)

    with pytest.raises(RuntimeError, match="commit explosion"):
        save_board_state(db, u.id, b.id, BoardStateSave(nodes=[_make_node("n1")], edges=[], expected_version=1))

    assert rollback_called, "rollback() debe llamarse tras fallo de commit()"
    assert not refresh_called, "refresh() no debe ejecutarse si commit() falla"


def test_session_usable_after_rollback(db, monkeypatch):
    """Después de rollback, la sesión debe permitir consultas normales."""
    u = _user(db)
    b = _board(db, u)

    def _failing_commit():
        raise RuntimeError("boom")

    monkeypatch.setattr(db, "commit", _failing_commit)

    with pytest.raises(RuntimeError):
        save_board_state(db, u.id, b.id, BoardStateSave(nodes=[_make_node("n1")], edges=[], expected_version=1))

    # La sesión debe seguir funcionando para consultas
    loaded = db.get(Board, b.id)
    assert loaded is not None
    assert loaded.id == b.id


def test_no_partial_state_after_constraint_violation(db, monkeypatch):
    """Una violación de constraint no debe dejar persistencia parcial."""
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="survivor", board_id=b.id))
    db.commit()

    # Forzar fallo en commit
    def _failing_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db, "commit", _failing_commit)

    with pytest.raises(RuntimeError):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1")],
            edges=[],
            expected_version=1,
        ))

    # El node anterior debe seguir existiendo
    db.rollback()  # recuperar sesión para la siguiente consulta
    assert db.get(Node, "survivor") is not None
    assert db.get(Node, "n1") is None


def test_updated_at_not_persisted_on_rollback(db, monkeypatch):
    """Si la transacción falla, updated_at no debe persistirse."""
    u = _user(db)
    b = _board(db, u)
    db.commit()
    before = b.updated_at

    def _failing_commit():
        raise RuntimeError("boom")

    monkeypatch.setattr(db, "commit", _failing_commit)

    with pytest.raises(RuntimeError):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1")],
            edges=[],
            expected_version=1,
        ))

    db.rollback()
    db.expire_all()
    board = db.get(Board, b.id)
    assert board.updated_at == before


# ======================================================================
# optimistic locking — versioning
# ======================================================================


def test_save_state_increments_version(db):
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(nodes=[], edges=[], expected_version=1))
    db.expire_all()
    board = db.get(Board, b.id)
    assert board.version == 2


def test_save_state_increments_version_once_per_call(db):
    u = _user(db)
    b = _board(db, u)
    # Multiple saves increment version by 1 each time
    save_board_state(db, u.id, b.id, BoardStateSave(
        nodes=[_make_node("n1"), _make_node("n2")],
        edges=[_make_edge("e1")],
        expected_version=1,
    ))
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_save_state_wrong_version_fails(db):
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="original", board_id=b.id))
    db.commit()
    with pytest.raises(VersionConflict):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1")],
            edges=[],
            expected_version=99,
        ))
    # Original state preserved
    assert db.get(Node, "original") is not None
    assert db.get(Node, "n1") is None


def test_save_state_conflict_preserves_previous_nodes(db):
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="n1", board_id=b.id))
    db.add(Node(id="n2", board_id=b.id))
    db.commit()
    with pytest.raises(VersionConflict):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n3")],
            edges=[],
            expected_version=99,
        ))
    assert db.get(Node, "n1") is not None
    assert db.get(Node, "n2") is not None


def test_save_state_conflict_preserves_previous_edges(db):
    u = _user(db)
    b = _board(db, u)
    db.add(Node(id="n1", board_id=b.id))
    db.add(Node(id="n2", board_id=b.id))
    db.add(Edge(id="e1", board_id=b.id, from_node="n1", from_port="p", to_node="n2", to_port="p"))
    db.commit()
    with pytest.raises(VersionConflict):
        save_board_state(db, u.id, b.id, BoardStateSave(
            nodes=[_make_node("n1"), _make_node("n2")],
            edges=[],
            expected_version=99,
        ))
    assert db.get(Edge, "e1") is not None


def test_save_state_conflict_preserves_name(db):
    u = _user(db)
    b = _board(db, u)
    with pytest.raises(VersionConflict):
        save_board_state(db, u.id, b.id, BoardStateSave(
            name="NewName",
            nodes=[],
            edges=[],
            expected_version=99,
        ))
    db.expire_all()
    assert db.get(Board, b.id).name == "B"


def test_save_state_version_rollback_on_failure(db, monkeypatch):
    """Si el guardado falla después del incremento, la versión se revierte."""
    u = _user(db)
    b = _board(db, u)

    def _failing_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db, "commit", _failing_commit)
    with pytest.raises(RuntimeError):
        save_board_state(db, u.id, b.id, BoardStateSave(nodes=[], edges=[], expected_version=1))
    db.rollback()
    db.expire_all()
    assert db.get(Board, b.id).version == 1


def test_save_state_version_outcome_in_response(db):
    """La respuesta de save_board_state incluye la nueva versión."""
    u = _user(db)
    b = _board(db, u)
    r = save_board_state(db, u.id, b.id, BoardStateSave(nodes=[], edges=[], expected_version=1))
    assert r.version == 2


def test_save_state_concurrent_conflict(db):
    """Dos saves con misma versión: primero funciona, segundo falla."""
    u = _user(db)
    b = _board(db, u)
    # Primero funciona
    save_board_state(db, u.id, b.id, BoardStateSave(nodes=[], edges=[], expected_version=1))
    # Segundo con versión obsoleta falla
    with pytest.raises(VersionConflict):
        save_board_state(db, u.id, b.id, BoardStateSave(nodes=[], edges=[], expected_version=1))
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_save_state_conflict_does_not_affect_other_board(db):
    u = _user(db)
    b1 = _board(db, u)
    b2 = _board(db, u)
    with pytest.raises(VersionConflict):
        save_board_state(db, u.id, b1.id, BoardStateSave(nodes=[], edges=[], expected_version=99))
    # b2 no afectado
    r = save_board_state(db, u.id, b2.id, BoardStateSave(nodes=[], edges=[], expected_version=1))
    assert r.version == 2
