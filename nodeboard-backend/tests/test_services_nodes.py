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
from app.services.nodes import create_node, create_nodes_batch, delete_node, move_node, update_node


@pytest.fixture()
def engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        try:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass

    Base.metadata.create_all(bind=engine)
    return engine


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


def test_create_node_with_preloaded_board(db):
    u = _user(db)
    b = _board(db, u)
    board = db.get(Board, b.id)
    result = create_node(
        db,
        u.id,
        b.id,
        _make_node(None, title="Precargado"),
        expected_version=1,
        board=board,
    )
    assert result.title == "Precargado"
    db.expire_all()
    assert db.get(Board, b.id).version == 2


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


def test_update_timeline_orientation(db):
    u = _user(db)
    b = _board(db, u)
    create_node(
        db,
        u.id,
        b.id,
        _make_node("t1", type="timeline", orientation="horizontal"),
        expected_version=1,
    )
    result = update_node(
        db,
        u.id,
        "t1",
        NodeUpdate(orientation="vertical"),
        expected_version=2,
    )
    assert result.orientation == "vertical"


def test_update_with_preloaded_node_and_board(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", title="Original"), expected_version=1)
    node = db.get(Node, "n1")
    board = db.get(Board, b.id)
    result = update_node(
        db,
        u.id,
        "n1",
        NodeUpdate(title="Precargado"),
        expected_version=2,
        node=node,
        board=board,
    )
    assert result.title == "Precargado"
    db.expire_all()
    assert db.get(Board, b.id).version == 3


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
# move_node
# ======================================================================


def test_move_node(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", x=10, y=20), expected_version=1)
    schema, prev, new = move_node(db, u.id, "n1", 300, 400, expected_version=2)
    assert schema.x == 300
    assert schema.y == 400
    assert prev == {"x": 10, "y": 20}
    assert new == {"x": 300, "y": 400}


def test_move_node_negative(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", x=0, y=0), expected_version=1)
    schema, _, _ = move_node(db, u.id, "n1", -150, -300, expected_version=2)
    assert schema.x == -150
    assert schema.y == -300


def test_move_node_float(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", x=0, y=0), expected_version=1)
    schema, _, _ = move_node(db, u.id, "n1", 100.5, 200.75, expected_version=2)
    assert schema.x == 100.5
    assert schema.y == 200.75


def test_move_node_preloaded(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", x=10, y=20), expected_version=1)
    node_obj = db.get(Node, "n1")
    board_obj = db.get(Board, b.id)
    schema, _, _ = move_node(
        db, u.id, "n1", 500, 600, expected_version=2,
        node=node_obj, board=board_obj,
    )
    assert schema.x == 500
    assert schema.y == 600


def test_move_node_other_user_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    ba = _board(db, a)
    create_node(db, a.id, ba.id, _make_node("n1"), expected_version=1)
    with pytest.raises(ResourceNotFound):
        move_node(db, b_user.id, "n1", 100, 200, expected_version=1)


def test_move_node_nonexistent_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        move_node(db, u.id, "no-such-id", 100, 200, expected_version=1)


def test_move_node_increments_version_once(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    move_node(db, u.id, "n1", 100, 200, expected_version=2)
    db.expire_all()
    assert db.get(Board, b.id).version == 3


def test_move_node_preserves_content(db):
    u = _user(db)
    b = _board(db, u)
    create_node(
        db, u.id, b.id,
        _make_node("n1", title="Original", w=300, tags=["a"], blocks=[{"id": "b1", "type": "text", "value": "Hello"}]),
        expected_version=1,
    )
    move_node(db, u.id, "n1", 100, 200, expected_version=2)
    db.expire_all()
    node = db.get(Node, "n1")
    assert node.title == "Original"
    assert node.w == 300
    assert node.tags == ["a"]
    assert node.blocks == [{"id": "b1", "type": "text", "value": "Hello"}]


def test_move_node_updates_timestamp(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)
    import time
    time.sleep(0.02)
    db.expire_all()
    board_before = db.get(Board, b.id)
    orig_updated = board_before.updated_at
    move_node(db, u.id, "n1", 100, 200, expected_version=2)
    db.expire_all()
    assert db.get(Board, b.id).updated_at > orig_updated


def test_move_node_wrong_version_fails(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", x=10, y=20), expected_version=1)
    with pytest.raises(VersionConflict):
        move_node(db, u.id, "n1", 100, 200, expected_version=99)
    db.expire_all()
    node = db.get(Node, "n1")
    assert node.x == 10
    assert node.y == 20


def test_move_node_rollback_reverts_version(db, monkeypatch):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", x=10, y=20), expected_version=1)

    def _failing_commit():
        raise RuntimeError("boom")

    monkeypatch.setattr(db, "commit", _failing_commit)
    with pytest.raises(RuntimeError):
        move_node(db, u.id, "n1", 300, 400, expected_version=2)
    db.rollback()
    db.expire_all()
    assert db.get(Board, b.id).version == 2  # versión incrementada antes del commit
    assert db.get(Node, "n1").x == 10
    assert db.get(Node, "n1").y == 20


def test_move_node_noop_increments_version(db):
    """Mover a la misma posición es semánticamente válido — incrementa versión."""
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1", x=100, y=200), expected_version=1)
    schema, prev, new = move_node(db, u.id, "n1", 100, 200, expected_version=2)
    assert schema.x == 100
    assert schema.y == 200
    assert prev == {"x": 100, "y": 200}
    assert new == {"x": 100, "y": 200}
    db.expire_all()
    assert db.get(Board, b.id).version == 3


def test_move_node_concurrent_conflict(engine):
    """Dos moves con misma versión: primero funciona, segundo falla."""
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup = TestingSession()
    try:
        u = _user(setup)
        user_id = u.id
        b = _board(setup, u)
        board_id = b.id
        create_node(setup, user_id, board_id, _make_node("n1", x=0, y=0), expected_version=1)
    finally:
        setup.close()

    db_a = TestingSession()
    db_b = TestingSession()
    try:
        move_node(db_a, user_id, "n1", 300, 400, expected_version=2)
        with pytest.raises(VersionConflict) as exc:
            move_node(db_b, user_id, "n1", 500, 600, expected_version=2)
        assert exc.value.expected_version == 2
        assert exc.value.current_version == 3

        verify = TestingSession()
        try:
            node = verify.get(Node, "n1")
            board = verify.get(Board, board_id)
            assert node.x == 300
            assert node.y == 400
            assert board.version == 3
        finally:
            verify.close()
    finally:
        db_a.close()
        db_b.close()


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


def test_update_node_rollback_reverts_version(db, monkeypatch):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, _make_node("n1"), expected_version=1)

    def _failing_commit():
        raise RuntimeError("boom")

    monkeypatch.setattr(db, "commit", _failing_commit)
    with pytest.raises(RuntimeError):
        update_node(db, u.id, "n1", NodeUpdate(title="X"), expected_version=2)
    db.rollback()
    db.expire_all()
    assert db.get(Board, b.id).version == 2
    assert db.get(Node, "n1").title == ""


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


def test_concurrent_create_node_with_two_sessions(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup = TestingSession()
    try:
        u = _user(setup)
        user_id = u.id
        b = _board(setup, u)
        board_id = b.id
    finally:
        setup.close()

    db_a = TestingSession()
    db_b = TestingSession()
    try:
        create_node(db_a, user_id, board_id, _make_node(None, title="A"), expected_version=1)
        with pytest.raises(VersionConflict) as exc:
            create_node(db_b, user_id, board_id, _make_node(None, title="B"), expected_version=1)
        assert exc.value.expected_version == 1
        assert exc.value.current_version == 2

        verify = TestingSession()
        try:
            nodes = verify.query(Node).filter(Node.board_id == board_id).all()
            board = verify.get(Board, board_id)
            assert len(nodes) == 1
            assert nodes[0].title == "A"
            assert board.version == 2
        finally:
            verify.close()
    finally:
        db_a.close()
        db_b.close()


def test_concurrent_update_node_with_two_sessions(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup = TestingSession()
    try:
        u = _user(setup)
        user_id = u.id
        b = _board(setup, u)
        board_id = b.id
        create_node(setup, user_id, board_id, _make_node("n1", title="Inicial"), expected_version=1)
    finally:
        setup.close()

    db_a = TestingSession()
    db_b = TestingSession()
    try:
        update_node(db_a, user_id, "n1", NodeUpdate(title="Título A"), expected_version=2)
        with pytest.raises(VersionConflict) as exc:
            update_node(db_b, user_id, "n1", NodeUpdate(title="Título B"), expected_version=2)
        assert exc.value.expected_version == 2
        assert exc.value.current_version == 3

        verify = TestingSession()
        try:
            node = verify.get(Node, "n1")
            board = verify.get(Board, board_id)
            assert node.title == "Título A"
            assert board.version == 3
        finally:
            verify.close()
    finally:
        db_a.close()
        db_b.close()


# ======================================================================
# create_nodes_batch
# ======================================================================


def _batch_payloads(*titles: str) -> list[NodeSchema]:
    return [
        NodeSchema(id=None, title=t, type="card", x=100 + i * 200, y=100)
        for i, t in enumerate(titles)
    ]


def test_create_nodes_batch_empty(db):
    u = _user(db)
    b = _board(db, u)
    result = create_nodes_batch(db, u.id, b.id, [], expected_version=1)
    assert len(result["nodes"]) == 0
    assert result["client_map"] == {}
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_create_nodes_batch_single_node(db):
    u = _user(db)
    b = _board(db, u)
    result = create_nodes_batch(
        db, u.id, b.id, _batch_payloads("Solo"), expected_version=1
    )
    assert len(result["nodes"]) == 1
    assert result["nodes"][0].title == "Solo"
    assert result["client_map"] == {0: result["nodes"][0].id}
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_create_nodes_batch_multiple(db):
    u = _user(db)
    b = _board(db, u)
    result = create_nodes_batch(
        db, u.id, b.id, _batch_payloads("A", "B", "C"), expected_version=1
    )
    assert len(result["nodes"]) == 3
    assert [n.title for n in result["nodes"]] == ["A", "B", "C"]
    assert len(result["client_map"]) == 3
    for i, n in enumerate(result["nodes"]):
        assert result["client_map"][i] == n.id


def test_create_nodes_batch_preserves_order(db):
    u = _user(db)
    b = _board(db, u)
    titles = ["Zeta", "Alfa", "Beta", "Gamma"]
    result = create_nodes_batch(
        db, u.id, b.id, _batch_payloads(*titles), expected_version=1
    )
    assert [n.title for n in result["nodes"]] == titles


def test_create_nodes_batch_positions_preserved(db):
    u = _user(db)
    b = _board(db, u)
    payloads = [
        NodeSchema(id=None, title="A", type="card", x=100, y=200),
        NodeSchema(id=None, title="B", type="card", x=500, y=300),
    ]
    result = create_nodes_batch(db, u.id, b.id, payloads, expected_version=1)
    assert result["nodes"][0].x == 100
    assert result["nodes"][0].y == 200
    assert result["nodes"][1].x == 500
    assert result["nodes"][1].y == 300


def test_create_nodes_batch_with_timeline(db):
    u = _user(db)
    b = _board(db, u)
    payloads = [
        NodeSchema(id=None, title="Card", type="card", x=0, y=0),
        NodeSchema(id=None, title="Timeline", type="timeline", x=400, y=0,
                    stages=[{"id": "s1", "title": "Etapa", "tags": ["x"]}]),
    ]
    result = create_nodes_batch(db, u.id, b.id, payloads, expected_version=1)
    assert result["nodes"][0].type == "card"
    assert result["nodes"][1].type == "timeline"
    assert len(result["nodes"][1].stages) == 1


def test_create_nodes_batch_generates_ids(db):
    u = _user(db)
    b = _board(db, u)
    result = create_nodes_batch(
        db, u.id, b.id, _batch_payloads("A", "B"), expected_version=1
    )
    for n in result["nodes"]:
        assert n.id is not None
        assert len(n.id) == 32
    assert result["nodes"][0].id != result["nodes"][1].id


def test_create_nodes_batch_increments_version_once(db):
    u = _user(db)
    b = _board(db, u)
    create_nodes_batch(db, u.id, b.id, _batch_payloads("A", "B", "C"), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_create_nodes_batch_boards_timestamp(db):
    u = _user(db)
    b = _board(db, u)
    original = b.updated_at
    import time
    time.sleep(0.02)
    create_nodes_batch(db, u.id, b.id, _batch_payloads("A"), expected_version=1)
    db.expire_all()
    assert db.get(Board, b.id).updated_at > original


def test_create_nodes_batch_preloaded_board(db):
    u = _user(db)
    b = _board(db, u)
    board_obj = db.get(Board, b.id)
    result = create_nodes_batch(
        db, u.id, b.id, _batch_payloads("Pre"), expected_version=1, board=board_obj
    )
    assert result["nodes"][0].title == "Pre"
    db.expire_all()
    assert db.get(Board, b.id).version == 2


def test_create_nodes_batch_wrong_version_fails(db):
    u = _user(db)
    b = _board(db, u)
    with pytest.raises(VersionConflict):
        create_nodes_batch(db, u.id, b.id, _batch_payloads("A"), expected_version=99)
    db.expire_all()
    assert db.get(Board, b.id).version == 1


def test_create_nodes_batch_other_board_fails(db):
    a = _user(db, "a@test.com")
    b_user = _user(db, "b@test.com")
    ba = _board(db, a)
    with pytest.raises(ResourceNotFound):
        create_nodes_batch(db, b_user.id, ba.id, _batch_payloads("A"), expected_version=1)


def test_create_nodes_batch_nonexistent_board_fails(db):
    u = _user(db)
    with pytest.raises(ResourceNotFound):
        create_nodes_batch(db, u.id, "no-such-board", _batch_payloads("A"), expected_version=1)


def test_create_nodes_batch_rollback_mid_batch(db, monkeypatch):
    u = _user(db)
    b = _board(db, u)

    def _failing_commit():
        raise RuntimeError("mid-batch boom")

    monkeypatch.setattr(db, "commit", _failing_commit)
    with pytest.raises(RuntimeError):
        create_nodes_batch(db, u.id, b.id, _batch_payloads("A", "B"), expected_version=1)
    db.rollback()
    db.expire_all()
    # No se crearon nodos ni se incrementó versión
    assert db.get(Board, b.id).version == 1
    assert db.query(Node).filter(Node.board_id == b.id).count() == 0


def test_create_nodes_batch_preserves_existing_nodes(db):
    u = _user(db)
    b = _board(db, u)
    create_node(db, u.id, b.id, NodeSchema(id="existing", title="Existente", type="card"),
                expected_version=1)
    result = create_nodes_batch(
        db, u.id, b.id, _batch_payloads("Nuevo"), expected_version=2
    )
    assert len(result["nodes"]) == 1
    db.expire_all()
    assert db.get(Node, "existing") is not None


def test_create_nodes_batch_with_ports_and_blocks(db):
    u = _user(db)
    b = _board(db, u)
    payloads = [
        NodeSchema(
            id=None, title="Con puertos", type="card",
            x=0, y=0,
            ports=[{"id": "p1", "side": "left", "color": "#4ADE80", "label": "In"}],
            blocks=[{"id": "b1", "type": "text", "value": "Hello"}],
            tags=["tag1"],
        ),
    ]
    result = create_nodes_batch(db, u.id, b.id, payloads, expected_version=1)
    n = result["nodes"][0]
    assert len(n.ports) == 1
    assert n.ports[0].label == "In"
    assert len(n.blocks) == 1
    assert n.blocks[0].value == "Hello"
    assert n.tags == ["tag1"]


def test_create_nodes_batch_concurrent_conflict(engine):
    """Dos batches con misma versión: primero funciona, segundo falla."""
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup = TestingSession()
    try:
        u = _user(setup)
        user_id = u.id
        b = _board(setup, u)
        board_id = b.id
    finally:
        setup.close()

    db_a = TestingSession()
    db_b = TestingSession()
    try:
        result_a = create_nodes_batch(
            db_a, user_id, board_id, _batch_payloads("Ganador"), expected_version=1
        )
        with pytest.raises(VersionConflict) as exc:
            create_nodes_batch(
                db_b, user_id, board_id, _batch_payloads("Perdedor"), expected_version=1
            )
        assert exc.value.expected_version == 1
        assert exc.value.current_version == 2
        assert len(result_a["nodes"]) == 1

        verify = TestingSession()
        try:
            nodes = verify.query(Node).filter(Node.board_id == board_id).all()
            board = verify.get(Board, board_id)
            assert len(nodes) == 1
            assert nodes[0].title == "Ganador"
            assert board.version == 2
        finally:
            verify.close()
    finally:
        db_a.close()
        db_b.close()
