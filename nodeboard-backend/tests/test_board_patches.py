"""Tests del planificador/validador de patches de board.

Cubre:
- modelos Pydantic (discriminador, campos extra, obligatorios)
- validación de endpoints (nodeId, clientId, ambos, ninguno)
- planificador build_board_patch_plan
- scopes, límites, versiones
- nodos (create, update, move) y edges (create, update)
- referencias internas (forward/backward)
- dry_run no muta nada
"""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Board, Edge, Node, Studio, User
from app.schemas import PortRef
from app.services.board_patches import (
    MCP_MAX_PATCH_OPERATIONS,
    BoardPatchPayload,
    EdgeEndpointClientRef,
    EdgeEndpointNodeRef,
    PatchCreateEdgeOperation,
    PatchCreateNodeOperation,
    PatchMoveNodeOperation,
    PatchUpdateEdgeOperation,
    PatchUpdateNodeOperation,
    build_board_patch_plan,
    required_scopes,
)
from app.services.errors import (
    OperationLimitExceeded,
    ValidationFailure,
    VersionConflict,
)


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


@pytest.fixture()
def user(db) -> User:
    u = User(
        id=uuid.uuid4().hex[:16],
        email="patch@test.com",
        name="Patch Tester",
        auth_provider="google",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def studio(db, user) -> Studio:
    s = Studio(id=uuid.uuid4().hex[:16], name="Patch Studio", color="azul",
               user_id=user.id)
    db.add(s)
    db.commit()
    return s


@pytest.fixture()
def board(db, user, studio) -> Board:
    b = Board(id=uuid.uuid4().hex[:16], name="Patch Board", studio_id=studio.id,
              version=5)
    db.add(b)
    db.commit()
    return b


@pytest.fixture()
def board_with_nodes(db, user, studio) -> Board:
    b = Board(id=uuid.uuid4().hex[:16], name="Board with nodes",
              studio_id=studio.id, version=5)
    n1 = Node(id="node-1", board_id=b.id, title="N1",
              x=10, y=20, w=280,
              ports=[{"id": "out", "side": "right", "color": "#60A5FA", "label": ""}])
    n2 = Node(id="node-2", board_id=b.id, title="N2",
              x=300, y=20, w=280,
              ports=[{"id": "in", "side": "left", "color": "#4ADE80", "label": ""}])
    db.add_all([b, n1, n2])
    db.commit()
    return b


# ======================================================================
# Helpers
# ======================================================================


def _make_payload(board_id, operations, expected_version=5, dry_run=True):
    return BoardPatchPayload(
        board_id=board_id,
        expected_version=expected_version,
        dry_run=dry_run,
        operations=operations,
    )


# ======================================================================
# Modelos Pydantic
# ======================================================================


class TestPatchModels:
    def test_create_node_discriminator(self):
        op = PatchCreateNodeOperation(
            op="create_node",
            client_id="n1",
            node={"type": "card", "title": "Test"},
        )
        assert op.op == "create_node"
        assert op.client_id == "n1"

    def test_create_node_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            PatchCreateNodeOperation(
                op="create_node",
                client_id="n1",
                node={"type": "card"},
                extra_field="nope",
            )

    def test_create_node_missing_client_id(self):
        with pytest.raises(ValidationError):
            PatchCreateNodeOperation(
                op="create_node",
                node={"type": "card"},
            )

    def test_update_node_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            PatchUpdateNodeOperation(
                op="update_node",
                node_id="n1",
                changes={"title": "New"},
                extra_field="nope",
            )

    def test_move_node_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            PatchMoveNodeOperation(
                op="move_node",
                node_id="n1",
                x=10, y=20,
                extra_field="nope",
            )

    def test_move_node_bool_coord_rejected(self):
        with pytest.raises(ValidationError):
            PatchMoveNodeOperation(
                op="move_node", node_id="n1", x=True, y=20,
            )

    def test_create_edge_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            PatchCreateEdgeOperation(
                op="create_edge",
                client_id="e1",
                edge={"from": {"nodeId": "n1", "portId": "out"},
                       "to": {"nodeId": "n2", "portId": "in"}},
                extra_field="nope",
            )

    def test_update_edge_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            PatchUpdateEdgeOperation(
                op="update_edge",
                edge_id="e1",
                changes={"label": "x"},
                extra_field="nope",
            )

    def test_unknown_op_rejected(self):
        with pytest.raises(ValidationError):
            BoardPatchPayload(
                board_id="b1",
                expected_version=1,
                dry_run=True,
                operations=[{"op": "delete_node", "node_id": "n1"}],
            )

    def test_empty_operations_rejected(self):
        with pytest.raises(ValidationError):
            BoardPatchPayload(
                board_id="b1",
                expected_version=1,
                dry_run=True,
                operations=[],
            )

    def test_board_payload_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            BoardPatchPayload(
                board_id="b1",
                expected_version=1,
                dry_run=True,
                operations=[{"op": "create_node", "client_id": "n1",
                              "node": {"type": "card"}}],
                extra_field="nope",
            )


# ======================================================================
# Edge endpoints
# ======================================================================


class TestEdgeEndpoints:
    def test_node_ref_valid(self):
        ep = EdgeEndpointNodeRef(nodeId="n1", portId="out")
        assert ep.nodeId == "n1"

    def test_client_ref_valid(self):
        ep = EdgeEndpointClientRef(clientId="new-node", portId="in")
        assert ep.clientId == "new-node"


# ======================================================================
# required_scopes
# ======================================================================


class TestRequiredScopes:
    def test_create_node_scope(self):
        ops = [PatchCreateNodeOperation(op="create_node", client_id="n1",
                                         node={"type": "card"})]
        assert required_scopes(ops) == {"nodes:create"}

    def test_update_node_scope(self):
        ops = [PatchUpdateNodeOperation(op="update_node", node_id="n1",
                                         changes={"title": "x"})]
        assert required_scopes(ops) == {"nodes:update"}

    def test_move_node_scope(self):
        ops = [PatchMoveNodeOperation(op="move_node", node_id="n1", x=10, y=20)]
        assert required_scopes(ops) == {"nodes:update"}

    def test_create_edge_scope(self):
        ops = [PatchCreateEdgeOperation(
            op="create_edge", client_id="e1",
            edge={"from": {"nodeId": "n1", "portId": "out"},
                   "to": {"nodeId": "n2", "portId": "in"}},
        )]
        assert required_scopes(ops) == {"edges:create"}

    def test_update_edge_scope(self):
        ops = [PatchUpdateEdgeOperation(
            op="update_edge", edge_id="e1", changes={"label": "x"},
        )]
        assert required_scopes(ops) == {"edges:update"}

    def test_multiple_scopes(self):
        ops = [
            PatchCreateNodeOperation(op="create_node", client_id="n1",
                                      node={"type": "card"}),
            PatchUpdateNodeOperation(op="update_node", node_id="n2",
                                      changes={"title": "x"}),
            PatchCreateEdgeOperation(
                op="create_edge", client_id="e1",
                edge={"from": {"nodeId": "n1", "portId": "out"},
                       "to": {"nodeId": "n2", "portId": "in"}},
            ),
        ]
        assert required_scopes(ops) == {"nodes:create", "nodes:update", "edges:create"}


# ======================================================================
# build_board_patch_plan
# ======================================================================


class TestPlanSuccess:
    def test_single_create_node(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "n1",
             "node": {"type": "card", "title": "Nuevo", "x": 100, "y": 200}},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.valid is True
        assert plan.dry_run is True
        assert plan.board_id == board.id
        assert plan.current_version == 5
        assert plan.predicted_version == 6
        assert plan.operation_count == 1
        assert plan.summary["nodes_created"] == 1
        assert "n1" in plan.client_references

    def test_single_create_timeline(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "tl1",
             "node": {"type": "timeline", "title": "Línea", "stages": []}},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.valid is True
        assert plan.summary["nodes_created"] == 1

    def test_single_update_node(self, db, user, board_with_nodes):
        b = board_with_nodes
        payload = _make_payload(b.id, [
            {"op": "update_node", "node_id": "node-1", "changes": {"title": "Updated"}},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.summary["nodes_updated"] == 1
        assert plan.summary["nodes_created"] == 0

    def test_single_move_node(self, db, user, board_with_nodes):
        b = board_with_nodes
        payload = _make_payload(b.id, [
            {"op": "move_node", "node_id": "node-1", "x": 500, "y": 600},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.summary["nodes_moved"] == 1

    def test_create_edge_with_real_ids(self, db, user, board_with_nodes):
        b = board_with_nodes
        payload = _make_payload(b.id, [
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"nodeId": "node-1", "portId": "out"},
                 "to": {"nodeId": "node-2", "portId": "in"},
             }},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.summary["edges_created"] == 1
        assert "e1" in plan.client_references

    def test_create_edge_with_client_id_refs(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "node-a",
             "node": {"type": "card", "title": "A", "x": 0, "y": 0}},
            {"op": "create_node", "client_id": "node-b",
             "node": {"type": "card", "title": "B", "x": 200, "y": 0}},
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"clientId": "node-a", "portId": "p"},
                 "to": {"clientId": "node-b", "portId": "p"},
             }},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.summary["nodes_created"] == 2
        assert plan.summary["edges_created"] == 1
        assert "node-a" in plan.client_references
        assert "node-b" in plan.client_references
        assert "e1" in plan.client_references

    def test_forward_reference(self, db, user, board):
        """Edge references a node created later in the operations list."""
        payload = _make_payload(board.id, [
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"clientId": "node-a", "portId": "p"},
                 "to": {"nodeId": "some-id", "portId": "p"},
             }},
            {"op": "create_node", "client_id": "node-a",
             "node": {"type": "card", "title": "Forward", "x": 0, "y": 0}},
        ])
        # Should fail because 'some-id' doesn't exist
        with pytest.raises(ValidationFailure, match="no encontrado"):
            build_board_patch_plan(db, user.id, payload)

    def test_mixed_operations(self, db, user, board_with_nodes):
        b = board_with_nodes
        from app.services.edges import create_edge as ce
        from app.schemas import EdgeSchema
        ce(db, user.id, b.id, EdgeSchema(id="edge-exist",
            from_=PortRef(nodeId="node-1", portId="out"),
            to=PortRef(nodeId="node-2", portId="in")),
            expected_version=5, board=b)
        db.expire_all()
        b2 = db.get(Board, b.id)
        # Board is now version 6
        payload2 = _make_payload(b2.id, [
            {"op": "create_node", "client_id": "new-node",
             "node": {"type": "card", "title": "Nuevo", "x": 100, "y": 100}},
            {"op": "update_node", "node_id": "node-1",
             "changes": {"title": "Actualizado"}},
            {"op": "move_node", "node_id": "node-2", "x": 500, "y": 300},
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"nodeId": "node-1", "portId": "out"},
                 "to": {"clientId": "new-node", "portId": "p"},
             }},
            {"op": "update_edge", "edge_id": "edge-exist",
             "changes": {"label": "actualizado"}},
        ], expected_version=6)
        plan = build_board_patch_plan(db, user.id, payload2, board=b2)
        assert plan.valid is True
        assert plan.summary == {
            "nodes_created": 1, "nodes_updated": 1, "nodes_moved": 1,
            "edges_created": 1, "edges_updated": 1,
        }
        assert len(plan.operations) == 5
        assert plan.predicted_version == 7

    def test_predicts_correct_version(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "n1",
             "node": {"type": "card"}},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.current_version == 5
        assert plan.predicted_version == 6

    def test_preserves_operation_order(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "a",
             "node": {"type": "card", "title": "A"}},
            {"op": "create_node", "client_id": "b",
             "node": {"type": "card", "title": "B"}},
            {"op": "create_node", "client_id": "c",
             "node": {"type": "card", "title": "C"}},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        ops = [o.index for o in plan.operations]
        assert ops == [0, 1, 2]


class TestPlanLiveNodeValidation:
    def test_create_card_valid(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "n1",
             "node": {"type": "card", "title": "Válido"}},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.valid is True

    def test_create_timeline_valid(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "t1",
             "node": {"type": "timeline", "title": "Válido", "stages": []}},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.valid is True

    def test_create_node_unknown_type(self, db, user, board):
        with pytest.raises(ValidationError):
            # This fails at Pydantic level for the operation
            _make_payload(board.id, [
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "unknown"}},
            ])

    def test_update_nonexistent_node(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "update_node", "node_id": "no-such", "changes": {"title": "x"}},
        ])
        with pytest.raises(ValidationFailure, match="no encontrado"):
            build_board_patch_plan(db, user.id, payload)

    def test_move_nonexistent_node(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "move_node", "node_id": "no-such", "x": 10, "y": 20},
        ])
        with pytest.raises(ValidationFailure, match="no encontrado"):
            build_board_patch_plan(db, user.id, payload)

    def test_update_changes_validated(self, db, user, board_with_nodes):
        b = board_with_nodes
        payload = _make_payload(b.id, [
            {"op": "update_node", "node_id": "node-1",
             "changes": {"invalid_field": "x"}},
        ])
        with pytest.raises((ValidationFailure, ValidationError)):
            build_board_patch_plan(db, user.id, payload)

    def test_duplicate_client_id_rejected(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "dup",
             "node": {"type": "card"}},
            {"op": "create_node", "client_id": "dup",
             "node": {"type": "card"}},
        ])
        with pytest.raises(ValidationFailure, match="duplicado"):
            build_board_patch_plan(db, user.id, payload)


class TestPlanEdgeValidation:
    def test_edge_to_nonexistent_node(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"nodeId": "no-such", "portId": "p"},
                 "to": {"nodeId": "no-such-2", "portId": "p"},
             }},
        ])
        with pytest.raises(ValidationFailure, match="no encontrado"):
            build_board_patch_plan(db, user.id, payload)

    def test_edge_with_client_id_to_nonexistent(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"clientId": "not-created", "portId": "p"},
                 "to": {"nodeId": "also-no-such", "portId": "p"},
             }},
        ])
        with pytest.raises(ValidationFailure, match="no encontrado"):
            build_board_patch_plan(db, user.id, payload)

    def test_edge_both_node_and_client_id_rejected(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"nodeId": "n1", "clientId": "n2", "portId": "p"},
                 "to": {"nodeId": "n3", "portId": "p"},
             }},
        ])
        with pytest.raises(ValidationFailure, match="no puede tener"):
            build_board_patch_plan(db, user.id, payload)

    def test_edge_neither_node_nor_client_id(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"portId": "p"},
                 "to": {"nodeId": "n2", "portId": "p"},
             }},
        ])
        with pytest.raises(ValidationFailure, match="debe tener"):
            build_board_patch_plan(db, user.id, payload)

    def test_self_edge_allowed(self, db, user, board_with_nodes):
        b = board_with_nodes
        payload = _make_payload(b.id, [
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"nodeId": "node-1", "portId": "out"},
                 "to": {"nodeId": "node-1", "portId": "out"},
             }},
        ])
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.valid is True
        assert any("self-edge" in w for w in plan.warnings)

    def test_edge_port_validation(self, db, user, board_with_nodes):
        b = board_with_nodes
        payload = _make_payload(b.id, [
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"nodeId": "node-1", "portId": "nonexistent"},
                 "to": {"nodeId": "node-2", "portId": "in"},
             }},
        ])
        with pytest.raises(ValidationFailure, match="Puerto"):
            build_board_patch_plan(db, user.id, payload)

    def test_edge_logical_port_validation(self, db, user, board):
        # First create an edge that references a node that will be
        # created in the patch, with an invalid port
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "source",
             "node": {"type": "card", "ports": [{"id": "out", "side": "right",
                                                  "color": "#60A5FA", "label": ""}]}},
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"clientId": "source", "portId": "missing"},
                 "to": {"clientId": "source", "portId": "out"},
             }},
        ])
        with pytest.raises(ValidationFailure, match="Puerto"):
            build_board_patch_plan(db, user.id, payload)

    def test_duplicate_edge_client_id_rejected(self, db, user, board_with_nodes):
        b = board_with_nodes
        payload = _make_payload(b.id, [
            {"op": "create_edge", "client_id": "dup",
             "edge": {
                 "from": {"nodeId": "node-1", "portId": "out"},
                 "to": {"nodeId": "node-2", "portId": "in"},
             }},
            {"op": "create_edge", "client_id": "dup",
             "edge": {
                 "from": {"nodeId": "node-1", "portId": "out"},
                 "to": {"nodeId": "node-2", "portId": "in"},
             }},
        ])
        with pytest.raises(ValidationFailure, match="duplicado"):
            build_board_patch_plan(db, user.id, payload)

    def test_edge_client_id_global_unique(self, db, user, board):
        """client_id no puede coincidir entre node y edge."""
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "shared",
             "node": {"type": "card"}},
            {"op": "create_edge", "client_id": "shared",
             "edge": {
                 "from": {"nodeId": "some", "portId": "p"},
                 "to": {"nodeId": "other", "portId": "p"},
             }},
        ])
        with pytest.raises(ValidationFailure, match="ya usado"):
            build_board_patch_plan(db, user.id, payload)


class TestPlanVersion:
    def test_wrong_version_fails(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "n1",
             "node": {"type": "card"}},
        ], expected_version=3)
        with pytest.raises(VersionConflict):
            build_board_patch_plan(db, user.id, payload)

    def test_version_not_incremented(self, db, user, board):
        """Dry-run no debe cambiar la versión."""
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "n1",
             "node": {"type": "card"}},
        ])
        build_board_patch_plan(db, user.id, payload)
        db.expire_all()
        assert db.get(Board, board.id).version == 5


class TestPlanLimit:
    def test_empty_operations_rejected(self, db, user, board):
        with pytest.raises(ValidationError):
            _make_payload(board.id, [])

    def test_over_limit_rejected(self, db, user, board):
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": f"n{i}",
                 "node": {"type": "card"}}
                for i in range(MCP_MAX_PATCH_OPERATIONS + 1)
            ],
        )
        with pytest.raises(OperationLimitExceeded):
            build_board_patch_plan(db, user.id, payload)

    def test_exact_limit_ok(self, db, user, board):
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=True,
            operations=[
                {"op": "create_node", "client_id": f"n{i}",
                 "node": {"type": "card"}}
                for i in range(MCP_MAX_PATCH_OPERATIONS)
            ],
        )
        plan = build_board_patch_plan(db, user.id, payload)
        assert plan.valid is True
        assert plan.operation_count == MCP_MAX_PATCH_OPERATIONS


class TestPlanNoMutation:
    def test_dry_run_does_not_create_nodes(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "n1",
             "node": {"type": "card", "title": "No persistir"}},
        ])
        build_board_patch_plan(db, user.id, payload)
        db.expire_all()
        nodes = db.query(Node).filter(Node.board_id == board.id).all()
        assert len(nodes) == 0

    def test_dry_run_does_not_change_timestamp(self, db, user, board):
        import time
        orig = board.updated_at
        time.sleep(0.02)
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "n1",
             "node": {"type": "card"}},
        ])
        build_board_patch_plan(db, user.id, payload)
        db.expire_all()
        assert db.get(Board, board.id).updated_at == orig

    def test_dry_run_twice_produces_same_plan(self, db, user, board):
        payload = _make_payload(board.id, [
            {"op": "create_node", "client_id": "n1",
             "node": {"type": "card", "title": "Consistente"}},
        ])
        plan1 = build_board_patch_plan(db, user.id, payload)
        plan2 = build_board_patch_plan(db, user.id, payload)
        assert plan1.operation_count == plan2.operation_count
        assert plan1.summary == plan2.summary
        assert plan1.current_version == plan2.current_version


# ======================================================================
# execute_board_patch
# ======================================================================


class TestExecuteSingleOperation:
    def test_create_node(self, db, user, board):
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=False,
            operations=[{"op": "create_node", "client_id": "n1",
                          "node": {"type": "card", "title": "Nuevo", "x": 100, "y": 200}}],
        )
        result = execute_board_patch(db, user.id, payload, board=board)
        assert result.applied is True
        assert result.dry_run is False
        assert result.board_id == board.id
        assert result.previous_version == 5
        assert result.board_version == 6
        assert result.operation_count == 1
        assert result.summary["nodes_created"] == 1
        assert "n1" in result.created
        assert result.created["n1"].resource_type == "node"
        assert result.created["n1"].id is not None
        assert len(result.operations) == 1
        assert result.operations[0].op == "create_node"
        assert result.operations[0].status == "applied"

        # Verify DB
        db.expire_all()
        board_db = db.get(Board, board.id)
        assert board_db.version == 6
        assert len(board_db.nodes) == 1
        assert board_db.nodes[0].title == "Nuevo"

    def test_update_node(self, db, user, board_with_nodes):
        b = board_with_nodes
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=b.id,
            expected_version=5,
            dry_run=False,
            operations=[{"op": "update_node", "node_id": "node-1",
                          "changes": {"title": "Updated"}}],
        )
        result = execute_board_patch(db, user.id, payload, board=b)
        assert result.summary["nodes_updated"] == 1
        db.expire_all()
        node = db.get(Node, "node-1")
        assert node.title == "Updated"
        assert db.get(Board, b.id).version == 6

    def test_move_node(self, db, user, board_with_nodes):
        b = board_with_nodes
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=b.id,
            expected_version=5,
            dry_run=False,
            operations=[{"op": "move_node", "node_id": "node-1", "x": 500, "y": 600}],
        )
        result = execute_board_patch(db, user.id, payload, board=b)
        assert result.summary["nodes_moved"] == 1
        db.expire_all()
        node = db.get(Node, "node-1")
        assert node.x == 500
        assert node.y == 600

    def test_create_edge(self, db, user, board_with_nodes):
        b = board_with_nodes
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=b.id,
            expected_version=5,
            dry_run=False,
            operations=[{"op": "create_edge", "client_id": "e1",
                          "edge": {
                              "from": {"nodeId": "node-1", "portId": "out"},
                              "to": {"nodeId": "node-2", "portId": "in"},
                          }}],
        )
        result = execute_board_patch(db, user.id, payload, board=b)
        assert result.summary["edges_created"] == 1
        assert "e1" in result.created
        assert result.created["e1"].resource_type == "edge"
        db.expire_all()
        assert len(db.get(Board, b.id).edges) == 1

    def test_update_edge(self, db, user, board_with_nodes):
        b = board_with_nodes
        from app.services.edges import create_edge as ce
        from app.schemas import EdgeSchema
        ce(db, user.id, b.id, EdgeSchema(id="edge-exist",
            from_={"nodeId": "node-1", "portId": "out"},
            to={"nodeId": "node-2", "portId": "in"}),
            expected_version=5, board=b)
        db.expire_all()
        b2 = db.get(Board, b.id)
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=b2.id,
            expected_version=6,
            dry_run=False,
            operations=[{"op": "update_edge", "edge_id": "edge-exist",
                          "changes": {"label": "updated"}}],
        )
        result = execute_board_patch(db, user.id, payload, board=b2)
        assert result.summary["edges_updated"] == 1
        db.expire_all()
        edge = db.get(Edge, "edge-exist")
        assert edge.label == "updated"


class TestExecuteMixedPatch:
    def test_mixed_operations(self, db, user, board_with_nodes):
        b = board_with_nodes
        from app.services.edges import create_edge as ce
        from app.schemas import EdgeSchema
        ce(db, user.id, b.id, EdgeSchema(id="edge-exist",
            from_={"nodeId": "node-1", "portId": "out"},
            to={"nodeId": "node-2", "portId": "in"}),
            expected_version=5, board=b)
        db.expire_all()
        b2 = db.get(Board, b.id)
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=b2.id,
            expected_version=6,
            dry_run=False,
            operations=[
                {"op": "create_node", "client_id": "new-node",
                 "node": {"type": "card", "title": "Nuevo", "x": 100, "y": 100}},
                {"op": "update_node", "node_id": "node-1",
                 "changes": {"title": "Actualizado"}},
                {"op": "move_node", "node_id": "node-2", "x": 500, "y": 300},
                {"op": "create_edge", "client_id": "e1",
                 "edge": {
                     "from": {"nodeId": "node-1", "portId": "out"},
                     "to": {"clientId": "new-node", "portId": "p"},
                 }},
                {"op": "update_edge", "edge_id": "edge-exist",
                 "changes": {"label": "actualizado"}},
            ],
        )
        result = execute_board_patch(db, user.id, payload, board=b2)
        assert result.summary == {
            "nodes_created": 1, "nodes_updated": 1, "nodes_moved": 1,
            "edges_created": 1, "edges_updated": 1,
        }
        assert result.operation_count == 5
        assert result.previous_version == 6
        assert result.board_version == 7
        assert "new-node" in result.created
        assert "e1" in result.created
        assert result.created["new-node"].resource_type == "node"
        assert result.created["e1"].resource_type == "edge"

        # Verify order
        for i, op in enumerate(result.operations):
            assert op.index == i

        # Verify DB
        db.expire_all()
        board_db = db.get(Board, b2.id)
        assert board_db.version == 7
        assert len(board_db.nodes) == 3  # 2 originales + 1 nuevo
        assert len(board_db.edges) == 2  # 1 existente + 1 nuevo
        assert db.get(Node, "node-1").title == "Actualizado"
        assert db.get(Node, "node-2").x == 500
        assert db.get(Edge, "edge-exist").label == "actualizado"

    def test_forward_reference(self, db, user, board):
        """Edge reference a node creado antes en el mismo patch."""
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=False,
            operations=[
                {"op": "create_node", "client_id": "node-a",
                 "node": {"type": "card", "title": "A"}},
                {"op": "create_node", "client_id": "node-b",
                 "node": {"type": "card", "title": "B",
                          "ports": [{"id": "p", "side": "left", "color": "#4ADE80", "label": ""}]}},
                {"op": "create_edge", "client_id": "e1",
                 "edge": {
                     "from": {"clientId": "node-a", "portId": "p"},
                     "to": {"clientId": "node-b", "portId": "p"},
                 }},
            ],
        )
        result = execute_board_patch(db, user.id, payload, board=board)
        assert result.summary["nodes_created"] == 2
        assert result.summary["edges_created"] == 1
        db.expire_all()
        assert len(db.get(Board, board.id).nodes) == 2
        assert len(db.get(Board, board.id).edges) == 1

    def test_backward_reference(self, db, user, board):
        """Edge reference a node creado después en el mismo patch."""
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=False,
            operations=[
                {"op": "create_edge", "client_id": "e1",
                 "edge": {
                     "from": {"clientId": "node-a", "portId": "p"},
                     "to": {"clientId": "node-b", "portId": "p"},
                 }},
                {"op": "create_node", "client_id": "node-a",
                 "node": {"type": "card", "title": "A"}},
                {"op": "create_node", "client_id": "node-b",
                 "node": {"type": "card", "title": "B",
                          "ports": [{"id": "p", "side": "left", "color": "#4ADE80", "label": ""}]}},
            ],
        )
        # Forward references are resolved at execution time because Phase A
        # generates all IDs first, but edge validation in Phase B checks
        # the nodes exist in the combined map
        result = execute_board_patch(db, user.id, payload, board=board)
        assert result.summary["nodes_created"] == 2
        assert result.summary["edges_created"] == 1

    def test_multiple_updates_in_order(self, db, user, board):
        from app.schemas import NodeSchema
        from app.services.nodes import create_node
        create_node(db, user.id, board.id, NodeSchema(id="n1", title="A"), expected_version=5, board=board)
        db.expire_all()
        b2 = db.get(Board, board.id)
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=b2.id,
            expected_version=6,
            dry_run=False,
            operations=[
                {"op": "update_node", "node_id": "n1",
                 "changes": {"title": "B"}},
                {"op": "update_node", "node_id": "n1",
                 "changes": {"title": "C"}},
            ],
        )
        result = execute_board_patch(db, user.id, payload, board=b2)
        assert result.summary["nodes_updated"] == 2
        db.expire_all()
        assert db.get(Node, "n1").title == "C"

    def test_multiple_moves_in_order(self, db, user, board):
        from app.schemas import NodeSchema
        from app.services.nodes import create_node
        create_node(db, user.id, board.id, NodeSchema(id="n1", x=0, y=0), expected_version=5, board=board)
        db.expire_all()
        b2 = db.get(Board, board.id)
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=b2.id,
            expected_version=6,
            dry_run=False,
            operations=[
                {"op": "move_node", "node_id": "n1", "x": 10, "y": 20},
                {"op": "move_node", "node_id": "n1", "x": 100, "y": 200},
            ],
        )
        result = execute_board_patch(db, user.id, payload, board=b2)
        assert result.summary["nodes_moved"] == 2
        db.expire_all()
        node = db.get(Node, "n1")
        assert node.x == 100
        assert node.y == 200

    def test_version_match(self, db, user, board):
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=False,
            operations=[{"op": "create_node", "client_id": "n1",
                          "node": {"type": "card"}}],
        )
        result = execute_board_patch(db, user.id, payload, board=board)
        assert result.previous_version == 5
        assert result.board_version == 6

    def test_version_conflict(self, db, user, board):
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        from app.services.errors import VersionConflict
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=3,
            dry_run=False,
            operations=[{"op": "create_node", "client_id": "n1",
                          "node": {"type": "card"}}],
        )
        with pytest.raises(VersionConflict):
            execute_board_patch(db, user.id, payload, board=board)
        db.expire_all()
        assert db.get(Board, board.id).version == 5  # unchanged


class TestExecuteRollback:
    def test_mid_patch_failure_at_beginning(self, db, user, board):
        """Fallar al crear un edge con puerto que no existe debe revertir todo."""
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        from app.services.errors import ValidationFailure
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=False,
            operations=[
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "A",
                          "ports": [{"id": "only-port", "side": "left",
                                      "color": "#4ADE80", "label": ""}]}},
                {"op": "create_edge", "client_id": "e1",
                 "edge": {
                     "from": {"clientId": "n1", "portId": "nonexistent"},
                     "to": {"clientId": "n1", "portId": "only-port"},
                 }},
            ],
        )
        with pytest.raises(ValidationFailure):
            execute_board_patch(db, user.id, payload, board=board)
        db.expire_all()
        board_db = db.get(Board, board.id)
        assert board_db.version == 5  # unchanged
        assert len(board_db.nodes) == 0  # no partial creation

    def test_mid_patch_failure_at_middle(self, db, user, board_with_nodes):
        """Tercera operación falla -> nada se persiste."""
        b = board_with_nodes
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        from app.services.errors import ValidationFailure
        payload = BoardPatchPayload(
            board_id=b.id,
            expected_version=5,
            dry_run=False,
            operations=[
                {"op": "create_node", "client_id": "n1",
                 "node": {"type": "card", "title": "A",
                          "ports": [{"id": "def-port", "side": "left",
                                      "color": "#4ADE80", "label": ""}]}},
                {"op": "update_node", "node_id": "node-1",
                 "changes": {"title": "Updated"}},
                {"op": "create_edge", "client_id": "e1",
                 "edge": {
                     "from": {"clientId": "n1", "portId": "bad-port"},
                     "to": {"nodeId": "node-2", "portId": "in"},
                 }},
                {"op": "move_node", "node_id": "node-2", "x": 999, "y": 999},
            ],
        )
        with pytest.raises(ValidationFailure):
            execute_board_patch(db, user.id, payload, board=b)
        db.expire_all()
        board_db = db.get(Board, b.id)
        assert board_db.version == 5
        assert len(board_db.nodes) == 2  # originales
        assert db.get(Node, "node-1").title == "N1"  # no updated
        assert db.get(Node, "node-2").x == 300  # not moved

    def test_version_conflict_rollback(self, db, user, board):
        """Conflicto de versión no deja cambios."""
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        from app.services.errors import VersionConflict
        # First modify the board to change its version
        from app.schemas import NodeSchema
        from app.services.nodes import create_node
        create_node(db, user.id, board.id, NodeSchema(id="other"), expected_version=5, board=board)
        db.expire_all()
        b2 = db.get(Board, board.id)
        assert b2.version == 6

        # Try with wrong version
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,  # wrong
            dry_run=False,
            operations=[{"op": "create_node", "client_id": "n1",
                          "node": {"type": "card"}}],
        )
        with pytest.raises(VersionConflict):
            execute_board_patch(db, user.id, payload, board=b2)
        db.expire_all()
        board_db = db.get(Board, board.id)
        assert board_db.version == 6  # unchanged
        assert len(board_db.nodes) == 1  # only the first node

    def test_concurrent_patches(self, db, user, board):
        """Dos patches concurrentes: uno gana, otro recibe VersionConflict."""
        from app.services.board_patches import execute_board_patch, BoardPatchPayload

        payload_a = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=False,
            operations=[{"op": "create_node", "client_id": "a",
                          "node": {"type": "card", "title": "From A"}}],
        )
        # ejecutar A primero
        result_a = execute_board_patch(db, user.id, payload_a, board=board)
        assert result_a.applied is True
        assert result_a.board_version == 6

        # B intenta con version anterior
        db.expire_all()
        b2 = db.get(Board, board.id)
        payload_b = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,  # obsoleto
            dry_run=False,
            operations=[{"op": "create_node", "client_id": "b",
                          "node": {"type": "card", "title": "From B"}}],
        )
        with pytest.raises(VersionConflict):
            execute_board_patch(db, user.id, payload_b, board=b2)

        # Verificar solo existe el nodo de A
        db.expire_all()
        board_db = db.get(Board, board.id)
        assert board_db.version == 6
        assert len(board_db.nodes) == 1
        assert board_db.nodes[0].title == "From A"


class TestExecutePortValidation:
    def test_validates_ports_against_constructed_model(self, db, user, board):
        """Los puertos se validan contra el modelo realmente construido."""
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        from app.services.errors import ValidationFailure
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=False,
            operations=[
                {"op": "create_node", "client_id": "source",
                 "node": {"type": "card", "title": "Source",
                          "ports": [{"id": "out", "side": "right",
                                      "color": "#60A5FA", "label": ""}]}},
                {"op": "create_edge", "client_id": "e1",
                 "edge": {
                     "from": {"clientId": "source", "portId": "missing"},
                     "to": {"clientId": "source", "portId": "out"},
                 }},
            ],
        )
        with pytest.raises(ValidationFailure, match="Puerto"):
            execute_board_patch(db, user.id, payload, board=board)
        db.expire_all()
        assert len(db.get(Board, board.id).nodes) == 0  # rollback

    def test_validates_ports_correctly_succeeds(self, db, user, board):
        """Puertos correctos no fallan."""
        from app.services.board_patches import execute_board_patch, BoardPatchPayload
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=False,
            operations=[
                {"op": "create_node", "client_id": "source",
                 "node": {"type": "card", "title": "Source",
                          "ports": [{"id": "out", "side": "right",
                                      "color": "#60A5FA", "label": ""}]}},
                {"op": "create_edge", "client_id": "e1",
                 "edge": {
                     "from": {"clientId": "source", "portId": "out"},
                     "to": {"clientId": "source", "portId": "out"},
                 }},
            ],
        )
        result = execute_board_patch(db, user.id, payload, board=board)
        assert result.applied is True
        assert result.summary["nodes_created"] == 1
        assert result.summary["edges_created"] == 1


class TestExecuteConsistencyDryRun:
    def test_summary_matches_dry_run(self, db, user, board_with_nodes):
        """El summary de dry_run y ejecución coinciden para el mismo payload."""
        b = board_with_nodes
        from app.services.board_patches import (
            build_board_patch_plan,
            execute_board_patch,
            BoardPatchPayload,
        )
        from app.services.edges import create_edge as ce
        from app.schemas import EdgeSchema
        ce(db, user.id, b.id, EdgeSchema(id="edge-exist",
            from_={"nodeId": "node-1", "portId": "out"},
            to={"nodeId": "node-2", "portId": "in"}),
            expected_version=5, board=b)
        db.expire_all()
        b2 = db.get(Board, b.id)

        operations = [
            {"op": "create_node", "client_id": "new-node",
             "node": {"type": "card", "title": "Nuevo"}},
            {"op": "update_node", "node_id": "node-1",
             "changes": {"title": "x"}},
            {"op": "move_node", "node_id": "node-2", "x": 100, "y": 200},
            {"op": "create_edge", "client_id": "e1",
             "edge": {
                 "from": {"nodeId": "node-1", "portId": "out"},
                 "to": {"clientId": "new-node", "portId": "p"},
             }},
            {"op": "update_edge", "edge_id": "edge-exist",
             "changes": {"label": "x"}},
        ]

        dry_payload = BoardPatchPayload(
            board_id=b2.id, expected_version=6, dry_run=True,
            operations=operations,
        )
        plan = build_board_patch_plan(db, user.id, dry_payload, board=b2)
        db.expire_all()
        b3 = db.get(Board, b2.id)

        exec_payload = BoardPatchPayload(
            board_id=b3.id, expected_version=6, dry_run=False,
            operations=operations,
        )
        result = execute_board_patch(db, user.id, exec_payload, board=b3)

        # Ambos summaries deben coincidir
        assert result.summary == plan.summary
        assert result.operation_count == plan.operation_count


class TestExecute100Operations:
    def test_one_commit_one_version(self, db, user, board):
        """100 operaciones en un solo commit y un solo incremento de versión."""
        from app.services.board_patches import execute_board_patch, BoardPatchPayload

        # Crear 20 nodos existentes (IDs reales) para update_node
        existing_ids = []
        for i in range(20):
            node = Node(id=uuid.uuid4().hex[:16], board_id=board.id,
                        title=f"Existing {i}", x=0, y=0)
            db.add(node)
            existing_ids.append(node.id)
        db.commit()
        db.expire_all()
        board = db.get(Board, board.id)  # version still 5

        ops = []
        for i in range(40):
            ops.append({
                "op": "create_node", "client_id": f"n{i}",
                "node": {"type": "card", "title": f"Node {i}",
                         "x": i * 10, "y": i * 20,
                         "ports": [{"id": "p", "side": "left",
                                     "color": "#4ADE80", "label": ""}]},
            })
        for i in range(40):
            ops.append({
                "op": "create_edge", "client_id": f"e{i}",
                "edge": {
                    "from": {"clientId": f"n{i}", "portId": "p"},
                    "to": {"clientId": f"n{(i+1) % 40}", "portId": "p"},
                },
            })
        for i, nid in enumerate(existing_ids):
            ops.append({
                "op": "update_node", "node_id": nid,
                "changes": {"title": f"Updated via patch {i}"},
            })

        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=5,
            dry_run=False,
            operations=ops,
        )
        result = execute_board_patch(db, user.id, payload, board=board)
        assert result.operation_count == 100
        assert result.summary["nodes_created"] == 40
        assert result.summary["edges_created"] == 40
        assert result.summary["nodes_updated"] == 20
        assert result.applied is True
        assert result.previous_version == 5
        assert result.board_version == 6

        # Verificar en DB
        db.expire_all()
        board_db = db.get(Board, board.id)
        assert board_db.version == 6
        assert len(board_db.nodes) == 60  # 20 existing + 40 new
        assert len(board_db.edges) == 40

        # Verificar updates aplicados
        for i, nid in enumerate(existing_ids):
            assert db.get(Node, nid).title == f"Updated via patch {i}"
