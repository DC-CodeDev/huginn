"""Tests unitarios del servicio de Nodes.

Cubre: creación (card/timeline/ajeno/inexistente/serialización),
actualización (todos los campos/parcial/ajeno/inexistente/Pydantic),
eliminación (propia/ajena/inexistente/cascada edges/transaccional),
verificación de board.updated_at, y optimistic locking.
"""
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Board, Edge, Node, Studio, User
from app.schemas import NodeSchema, NodeUpdate, Port, TextBlock, TimelineStage
from app.services.errors import ResourceNotFound, VersionConflict
from app.services.nodes import create_node, delete_node, update_node


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


def _make_node(node_id="n1", **overrides) -> NodeSchema:
    return NodeSchema(id=node_id, **overrides)


# ======================================================================
# create_node
# ======================================================================


def test_create_card_node(db):
    u = _user(db)
    b = _board(db, u)
    result = create_node(db, u.id, b.id, _make_node("n1", title="Card"), expected_version=1)
    assert result.id == "n1"
    assert result.type == "card"
    assert result.title == "Card"
    assert result.x == 0


def test_create_timeline_node(db):
    u = _user(db)
    b = _board(db, u)
    result = create_node(
        db, u.id, b.id,
        _make_node("t1", type="timeline", title="Timeline"),
        expected_version=1,
    )
    assert result.type == "timeline"
    assert result.title == "Timeline"


def test_create_node_other_board_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    b = _board(db, a)
    with pytest.raises(ResourceNotFound):
        create_node(db, b_user.id, b.id, _make_node("n1"), expected_version=1)


def test_create_node_nonexistent_board_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        create_node(db, u.id, "no-such-board", _make_node("n1"), expected_version=1)


def test_create_node_generates_id(db):
    u = _user(db)
    b = _board(db, u)
    result = create_node(db, u.id, b.id, _make_node(None), expected_version=1)
    assert result.id is not None
    assert len(result.id) == 32


def test_create_node_sets_board_id(db):
    u = _user(db)
    b = _board(db, u)
    result = create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    db.expire_all()
    node = db.get(Node, "n1")
    assert node.board_id == b.id


def test_create_node_updates_board_timestamp(db):
    u = _user(db)
    b = _board(db, u)
    original_updated = b.updated_at
    import time
    time.sleep(0.02)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    db.expire_all()
    board = db.get(Board, b.id)
    assert board.updated_at > original_updated


def test_create_node_persists(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", title="Persist"), expected_version=1)
    db.expire_all()
    loaded = db.get(Node, "n1")
    assert loaded is not None
    assert loaded.title == "Persist"


def test_create_node_with_ports(db):
    u = _user(db)
    b = _board(db, u)
    result = create_node(
        db, u.id, b.id,
        _make_node("n1", ports=[{"id": "p1", "side": "left", "color": "#4ADE80", "label": "In"}]),
        expected_version=1,
    )
    assert len(result.ports) == 1
    assert result.ports[0].color == "#4ADE80"
    assert result.ports[0].label == "In"


def test_create_node_with_blocks(db):
    u = _user(db)
    b = _board(db, u)
    result = create_node(
        db, u.id, b.id,
        _make_node("n1", blocks=[{"id": "b1", "type": "text", "value": "Hello"}]),
        expected_version=1,
    )
    assert len(result.blocks) == 1
    assert result.blocks[0].type == "text"
    assert result.blocks[0].value == "Hello"


def test_create_node_with_image_block(db):
    u = _user(db)
    b = _board(db, u)
    result = create_node(
        db, u.id, b.id,
        _make_node("img1", blocks=[{"id": "b1", "type": "image", "src": "data:img/png;base64,x"}]),
        expected_version=1,
    )
    assert result.blocks[0].type == "image"
    assert result.blocks[0].src == "data:img/png;base64,x"


def test_create_node_with_stages(db):
    u = _user(db)
    b = _board(db, u)
    result = create_node(
        db, u.id, b.id,
        _make_node("t1", type="timeline", stages=[{"id": "s1", "title": "Paso", "tags": ["x"]}]),
        expected_version=1,
    )
    assert len(result.stages) == 1
    assert result.stages[0].title == "Paso"
    assert result.stages[0].tags == ["x"]


def test_create_node_with_tags(db):
    u = _user(db)
    b = _board(db, u)
    result = create_node(
        db, u.id, b.id,
        _make_node("n1", tags=["alpha", "beta"]),
        expected_version=1,
    )
    assert result.tags == ["alpha", "beta"]


# ======================================================================
# update_node
# ======================================================================


def test_update_title(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", title="Original"), expected_version=1)
    result = update_node(db, u.id, "n1", NodeUpdate(title="Nuevo"), expected_version=2)
    assert result.title == "Nuevo"


def test_update_position(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", x=10, y=20), expected_version=1)
    result = update_node(db, u.id, "n1", NodeUpdate(x=100, y=200), expected_version=2)
    assert result.x == 100
    assert result.y == 200


def test_update_width(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", w=280), expected_version=1)
    result = update_node(db, u.id, "n1", NodeUpdate(w=400), expected_version=2)
    assert result.w == 400


def test_update_blocks(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", blocks=[{"id": "b1", "type": "text", "value": "Old"}]), expected_version=1)
    result = update_node(db, u.id, "n1", NodeUpdate(blocks=[{"id": "b2", "type": "text", "value": "New"}]), expected_version=2)
    assert len(result.blocks) == 1
    assert result.blocks[0].value == "New"


def test_update_stages(db):
    u = _user(db)
    b = _board(db, u)
    create_node(
        db, u.id, b.id,
        _make_node("t1", type="timeline", stages=[{"id": "s1", "title": "A", "tags": []}]),
        expected_version=1,
    )
    result = update_node(
        db, u.id, "t1",
        NodeUpdate(stages=[{"id": "s2", "title": "B", "tags": ["x"]}]),
        expected_version=2,
    )
    assert result.stages[0].title == "B"


def test_update_ports(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    result = update_node(
        db, u.id, "n1",
        NodeUpdate(ports=[{"id": "p1", "side": "right", "color": "#C084FC", "label": "Out"}]),
        expected_version=2,
    )
    assert len(result.ports) == 1
    assert result.ports[0].side == "right"


def test_update_tags(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", tags=["old"]), expected_version=1)
    result = update_node(db, u.id, "n1", NodeUpdate(tags=["new1", "new2"]), expected_version=2)
    assert result.tags == ["new1", "new2"]


def test_update_tags_null_clears(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", tags=["keep"]), expected_version=1)
    result = update_node(db, u.id, "n1", NodeUpdate(tags=None), expected_version=2)
    assert result.tags == []


def test_update_preserves_unchanged_fields(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", title="T", x=10, tags=["a"]), expected_version=1)
    result = update_node(db, u.id, "n1", NodeUpdate(title="New"), expected_version=2)
    assert result.title == "New"
    assert result.x == 10  # no enviado → preservado
    db.expire_all()
    node = db.get(Node, "n1")
    assert node.tags == ["a"]  # preservado


def test_update_other_user_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    ba = _board(db, a)
    create_node(db, a.id, ba.id, _make_node("n1"), expected_version=1)
    with pytest.raises(ResourceNotFound):
        update_node(db, b_user.id, "n1", NodeUpdate(title="Hack"), expected_version=1)


def test_update_nonexistent_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        update_node(db, u.id, "no-such-node", NodeUpdate(title="Nope"), expected_version=1)


def test_update_board_timestamp(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    import time
    time.sleep(0.02)
    db.expire_all()
    board_before = db.get(Board, b.id)
    orig_updated = board_before.updated_at
    update_node(db, u.id, "n1", NodeUpdate(title="Updated"), expected_version=2)
    db.expire_all()
    assert db.get(Board, b.id).updated_at > orig_updated


# ======================================================================
# delete_node
# ======================================================================


def test_delete_own_node(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    delete_node(db, u.id, "n1", expected_version=2)
    assert db.get(Node, "n1") is None


def test_delete_other_user_node_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    ba = _board(db, a)
    create_node(db, a.id, ba.id, _make_node("n1"), expected_version=1)
    with pytest.raises(ResourceNotFound):
        delete_node(db, b_user.id, "n1", expected_version=1)
    assert db.get(Node, "n1") is not None


def test_delete_nonexistent_node_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        delete_node(db, u.id, "no-such-id", expected_version=1)


def test_delete_removes_outgoing_edges(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    create_node(db, u.id, b.id, _make_node("n2"), expected_version=2)
    edge = Edge(id="e1", board_id=b.id, from_node="n1", from_port="p", to_node="n2", to_port="p")
    db.add(edge)
    db.commit()
    delete_node(db, u.id, "n1", expected_version=3)
    assert db.get(Edge, "e1") is None


def test_delete_removes_incoming_edges(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    create_node(db, u.id, b.id, _make_node("n2"), expected_version=2)
    edge = Edge(id="e1", board_id=b.id, from_node="n1", from_port="p", to_node="n2", to_port="p")
    db.add(edge)
    db.commit()
    delete_node(db, u.id, "n2", expected_version=3)
    assert db.get(Edge, "e1") is None


def test_delete_does_not_remove_unrelated_edges(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    create_node(db, u.id, b.id, _make_node("n2"), expected_version=2)
    create_node(db, u.id, b.id, _make_node("n3"), expected_version=3)
    e1 = Edge(id="e1", board_id=b.id, from_node="n1", from_port="p", to_node="n2", to_port="p")
    e2 = Edge(id="e2", board_id=b.id, from_node="n2", from_port="p", to_node="n3", to_port="p")
    db.add(e1)
    db.add(e2)
    db.commit()
    delete_node(db, u.id, "n1", expected_version=4)
    assert db.get(Edge, "e1") is None
    assert db.get(Edge, "e2") is not None


def test_delete_does_not_affect_other_boards(db):
    u = _user(db)
    b1 = _board(db, u)
    b2 = _board(db, u)
    create_node(db, u.id, b1.id, _make_node("n1"), expected_version=1)
    create_node(db, u.id, b2.id, _make_node("n2"), expected_version=1)
    delete_node(db, u.id, "n1", expected_version=2)
    assert db.get(Node, "n2") is not None


# ======================================================================
# optimistic locking — versioning
# ======================================================================


def test_create_node_increments_version(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_update_node_increments_version(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    update_node(db, u.id, "n1", NodeUpdate(title="X"), expected_version=2)
    db.expire_all()
    assert db.get(Board, b.id).version == 3


def test_delete_node_increments_version(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    delete_node(db, u.id, "n1", expected_version=2)
    db.expire_all()
    assert db.get(Board, b.id).version == 3


def test_create_node_wrong_version_fails(db):
    u = _user(db)
    b = _board(db, u)
    with pytest.raises(VersionConflict):
        create_node(db, u.id, b.id, _make_node("n1"), expected_version=99)
    assert db.get(Node, "n1") is None


def test_update_node_wrong_version_fails(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", title="Original"), expected_version=1)
    with pytest.raises(VersionConflict):
        update_node(db, u.id, "n1", NodeUpdate(title="X"), expected_version=99)
    db.expire_all()
    assert db.get(Node, "n1").title == "Original"


def test_delete_node_wrong_version_fails(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    with pytest.raises(VersionConflict):
        delete_node(db, u.id, "n1", expected_version=99)
    assert db.get(Node, "n1") is not None


def test_create_node_rollback_reverts_version(db, monkeypatch):
    u = _user(db)
    b = _board(db, u)

    def _failing_commit():
        raise RuntimeError("boom")

    monkeypatch.setattr(db, "commit", _failing_commit)
    with pytest.raises(RuntimeError):
        create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    db.rollback()
    db.expire_all()
    assert db.get(Board, b.id).version == 1
    assert db.get(Node, "n1") is None


def test_node_ops_increment_exactly_one(db):
    """Cada operación de node incrementa exactamente 1."""
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).version == 2
    update_node(db, u.id, "n1", NodeUpdate(title="X"), expected_version=2)
    db.expire_all()
    assert db.get(Board, b.id).version == 3


def test_concurrent_create_node_conflict(db):
    """Dos creates con misma versión: primero funciona, segundo falla."""
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    with pytest.raises(VersionConflict):
        create_node(db, u.id, b.id, _make_node("n2"), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).version == 2
