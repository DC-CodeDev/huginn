"""Tests end-to-end de propagación de `tags` (Node) y `label` (Edge) — Fase 1 Paso 3.

Validan el contrato DB ↔ API llamando las funciones de ruta con una SQLite
temporal. Así se evita el bootstrap ASGI/lifespan del backend, que en este
entorno queda bloqueado, sin perder la semántica real de persistencia.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.main import (
    create_board,
    create_edge,
    create_node,
    get_board,
    save_board_state,
    update_edge,
    update_node,
)
from app.schemas import BoardCreate, BoardStateSave, EdgeSchema, EdgeUpdate, NodeSchema, NodeUpdate, Port, PortRef


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


def _board(db) -> str:
    return create_board(BoardCreate(name="B"), db).id


def _make_node(node_id: str, **overrides) -> NodeSchema:
    return NodeSchema(
        id=node_id,
        title=overrides.pop("title", ""),
        tags=overrides.pop("tags", []),
        **overrides,
    )


def _board_with_edge(db, label="inicial", curved=True):
    """Crea board + dos nodos + una edge `e1`, y devuelve el board_id."""
    bid = _board(db)
    create_node(bid, _make_node("n1"), db)
    create_node(bid, _make_node("n2"), db)
    create_edge(
        bid,
        EdgeSchema(
            id="e1",
            from_=PortRef(nodeId="n1", portId="p"),
            to=PortRef(nodeId="n2", portId="p"),
            curved=curved,
            label=label,
        ),
        db,
    )
    return bid


def test_create_node_tags_roundtrip(db):
    bid = _board(db)
    created = create_node(bid, _make_node("n1", tags=["alpha", "beta"]), db)
    assert created.tags == ["alpha", "beta"]
    # Se lee igual desde el estado completo del tablero
    node = get_board(bid, db).nodes[0]
    assert node.tags == ["alpha", "beta"]


def test_create_node_without_tags_defaults_empty(db):
    bid = _board(db)
    created = create_node(bid, _make_node("n1"), db)
    assert created.tags == []


def test_create_edge_label_roundtrip(db):
    bid = _board(db)
    create_node(bid, _make_node("n1"), db)
    create_node(bid, _make_node("n2"), db)
    created = create_edge(
        bid,
        EdgeSchema(
            id="e1",
            from_=PortRef(nodeId="n1", portId="p"),
            to=PortRef(nodeId="n2", portId="p"),
            label="depende de",
        ),
        db,
    )
    assert created.label == "depende de"
    assert get_board(bid, db).edges[0].label == "depende de"


def test_create_edge_without_label_defaults_empty(db):
    bid = _board(db)
    create_node(bid, _make_node("n1"), db)
    create_node(bid, _make_node("n2"), db)
    created = create_edge(
        bid,
        EdgeSchema(
            id="e1",
            from_=PortRef(nodeId="n1", portId="p"),
            to=PortRef(nodeId="n2", portId="p"),
        ),
        db,
    )
    assert created.label == ""


def test_save_board_state_propagates_tags_and_label(db):
    bid = _board(db)
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
    )
    save_board_state(bid, state, db)
    board = get_board(bid, db)
    nodes = {n.id: n for n in board.nodes}
    assert nodes["n1"].tags == ["x", "y"]
    assert nodes["n2"].tags == []       # sin tags -> default
    assert board.edges[0].label == "conecta"


def test_update_node_tags_absent_preserves(db):
    """PATCH sin la clave `tags` no debe pisar el valor existente."""
    bid = _board(db)
    create_node(bid, _make_node("n1", tags=["keep"]), db)
    update_node("n1", NodeUpdate(title="nuevo"), db)
    node = get_board(bid, db).nodes[0]
    assert node.title == "nuevo"
    assert node.tags == ["keep"]


def test_update_node_tags_present_updates(db):
    bid = _board(db)
    create_node(bid, _make_node("n1", tags=["old"]), db)
    assert update_node("n1", NodeUpdate(tags=["new1", "new2"]), db).tags == ["new1", "new2"]


def test_update_node_tags_null_clears(db):
    """`tags: null` explícito es distinto de ausente: limpia a lista vacía (no 500)."""
    bid = _board(db)
    create_node(bid, _make_node("n1", tags=["will", "clear"]), db)
    resp = update_node("n1", NodeUpdate(tags=None), db)
    assert resp.tags == []


def test_update_edge_label_absent_preserves(db):
    """PATCH sin la clave `label` no debe pisar el valor existente."""
    bid = _board_with_edge(db, label="conserva")
    update_edge("e1", EdgeUpdate(curved=False), db)
    edge = get_board(bid, db).edges[0]
    assert edge.label == "conserva"
    assert edge.curved is False


def test_update_edge_label_present_updates(db):
    """PATCH solo `label` lo actualiza y persiste, sin afectar `curved`."""
    bid = _board_with_edge(db, label="viejo", curved=True)
    resp = update_edge("e1", EdgeUpdate(label="nuevo"), db)
    assert resp.label == "nuevo"
    edge = get_board(bid, db).edges[0]
    assert edge.label == "nuevo"
    assert edge.curved is True  # curved intacto


def test_update_edge_label_null_clears(db):
    """`label: null` explícito vacía a "" (no 500); mismo criterio que tags."""
    bid = _board_with_edge(db, label="a borrar")
    resp = update_edge("e1", EdgeUpdate(label=None), db)
    assert resp.label == ""


# --------------------------------------------------------- serialización JSON
# Regresión del bug del Paso 4: NodeSchema.ports/blocks/stages son modelos
# Pydantic, no dicts; asignarlos directo a la columna JSON rompía en commit con
# "Object of type Port is not JSON serializable". El fix aplana con model_dump().
# Ningún test previo ejercitaba este camino con ports/blocks no triviales.

def _node_with_ports(node_id: str) -> NodeSchema:
    return NodeSchema(
        id=node_id,
        title="Con puertos",
        ports=[
            Port(id="p1", side="left", color="#4ADE80", label="in"),
            Port(id="p2", side="right", color="#60A5FA", label="out"),
        ],
        blocks=[{"id": "b1", "type": "text", "value": "hola"}],
        tags=["t"],
    )


def test_save_board_state_with_real_ports_and_blocks_persists(db):
    bid = _board(db)
    edge = EdgeSchema(
        id="e1",
        from_=PortRef(nodeId="n1", portId="p2"),
        to=PortRef(nodeId="n2", portId="p1"),
        label="conecta",
    )
    state = BoardStateSave(nodes=[_node_with_ports("n1"), _node_with_ports("n2")], edges=[edge])
    save_board_state(bid, state, db)  # antes: TypeError en commit
    saved = get_board(bid, db).nodes[0]
    assert saved.ports[0].label == "in"
    assert saved.ports[1].label == "out"
    assert saved.blocks[0].value == "hola"
    assert saved.tags == ["t"]


def test_create_node_with_real_ports_persists(db):
    bid = _board(db)
    created = create_node(bid, _node_with_ports("n1"), db)  # antes: TypeError en commit
    assert created.ports[0].label == "in"
    relido = get_board(bid, db).nodes[0]
    assert relido.blocks[0].value == "hola"
