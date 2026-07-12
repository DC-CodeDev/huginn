"""Tests de integración del orquestador idempotente de apply_board_patch."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

import app.services.board_patches as board_patches
from app.database import Base
from app.models import Board, MCPAuditLog, MCPIdempotencyRecord, MCPToken, Node, Studio, User
from app.services.authorization import get_owned_board
from app.services.board_patches import (
    BoardPatchPayload,
    build_apply_board_patch_idempotency_payload,
    execute_idempotent_board_patch,
    validate_apply_board_patch_contract,
)
from app.services.errors import (
    IdempotencyConflict,
    IdempotencyInProgress,
    IdempotencyStateUncertain,
    ValidationFailure,
    VersionConflict,
)
from app.services.mcp_idempotency import build_idempotency_request_hash


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def SessionLocal(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db(SessionLocal):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def user(db) -> User:
    item = User(
        id=uuid.uuid4().hex[:16],
        email="patch-idem@test.com",
        name="Patch Idem",
        auth_provider="google",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def studio(db, user) -> Studio:
    item = Studio(
        id=uuid.uuid4().hex[:16],
        name="Studio",
        color="blue",
        user_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def board(db, studio) -> Board:
    item = Board(
        id=uuid.uuid4().hex[:16],
        name="Board",
        studio_id=studio.id,
        version=1,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def token(db, user) -> MCPToken:
    item = MCPToken(
        id=uuid.uuid4().hex[:16],
        user_id=user.id,
        name="Token",
        token_prefix="huginn_mcp_patch",
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        scopes=["nodes:create", "nodes:update", "edges:create", "edges:update"],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _payload(board_id: str, *, expected_version: int = 1, idempotency_key: str | None = None):
    return BoardPatchPayload(
        board_id=board_id,
        expected_version=expected_version,
        dry_run=False,
        idempotency_key=idempotency_key,
        operations=[
            {
                "op": "create_node",
                "client_id": "diagnostico",
                "node": {
                    "type": "card",
                    "title": "Diagnóstico",
                    "x": 100,
                    "y": 200,
                    "w": 280,
                    "ports": [
                        {"id": "out", "side": "right", "color": "#60A5FA", "label": ""}
                    ],
                    "tags": [],
                    "blocks": [],
                },
            }
        ],
    )


class TestContractAndHash:
    def test_dry_run_false_requires_key(self, board):
        payload = _payload(board.id, idempotency_key=None)
        with pytest.raises(ValidationFailure, match="idempotency_key es obligatoria"):
            validate_apply_board_patch_contract(payload)

    def test_dry_run_true_rejects_key(self, board):
        payload = BoardPatchPayload(
            board_id=board.id,
            expected_version=1,
            dry_run=True,
            idempotency_key="patch-key-100",
            operations=[{"op": "create_node", "client_id": "n1", "node": {"type": "card"}}],
        )
        with pytest.raises(ValidationFailure, match="no está permitida"):
            validate_apply_board_patch_contract(payload)

    @pytest.mark.parametrize(
        ("key", "message"),
        [
            ("", "no puede estar vacío"),
            ("short", "al menos 8 caracteres"),
            ("x" * 129, "no puede superar 128 caracteres"),
        ],
    )
    def test_invalid_key_is_rejected(self, board, key, message):
        payload = _payload(board.id, idempotency_key=key)
        with pytest.raises(ValidationFailure, match=message):
            validate_apply_board_patch_contract(payload)

    def test_hash_includes_expected_version_and_aliases(self, user, token, board):
        payload_a = BoardPatchPayload(
            board_id=board.id,
            expected_version=1,
            dry_run=False,
            idempotency_key="patch-key-101",
            operations=[
                {
                    "op": "create_edge",
                    "client_id": "edge-1",
                    "edge": {
                        "from": {"nodeId": "node-a", "portId": "out"},
                        "to": {"clientId": "node-b", "portId": "in"},
                    },
                }
            ],
        )
        payload_b = BoardPatchPayload(
            board_id=board.id,
            expected_version=1,
            dry_run=False,
            idempotency_key="patch-key-101-other",
            operations=[
                {
                    "op": "create_edge",
                    "client_id": "edge-1",
                    "edge": {
                        "to": {"clientId": "node-b", "portId": "in"},
                        "from": {"nodeId": "node-a", "portId": "out"},
                    },
                }
            ],
        )
        digest_a = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=build_apply_board_patch_idempotency_payload(payload_a),
            user_id=user.id,
            token_id=token.id,
        )
        digest_b = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=build_apply_board_patch_idempotency_payload(payload_b),
            user_id=user.id,
            token_id=token.id,
        )
        digest_c = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=build_apply_board_patch_idempotency_payload(
                BoardPatchPayload(
                    board_id=board.id,
                    expected_version=2,
                    dry_run=False,
                    idempotency_key="patch-key-101-third",
                    operations=payload_a.model_dump()["operations"],
                )
            ),
            user_id=user.id,
            token_id=token.id,
        )
        assert digest_a == digest_b
        assert digest_a != digest_c


class TestExecuteIdempotentBoardPatch:
    def test_new_execution_completes_and_stores_response(self, SessionLocal, user, token, board):
        payload = _payload(board.id, idempotency_key="patch-key-201")
        response = execute_idempotent_board_patch(
            SessionLocal,
            user_id=user.id,
            token_id=token.id,
            payload=payload,
            request_id="req-success",
            client_name="pytest-client",
            scope_validator=lambda operations: None,
            board_loader=lambda db: get_owned_board(db, user.id, board.id),
        )
        assert response["ok"] is True
        assert response["data"]["previous_version"] == 1
        assert response["data"]["board_version"] == 2

        with SessionLocal() as check:
            board_db = check.get(Board, board.id)
            record = check.execute(select(MCPIdempotencyRecord)).scalars().one()
            audit = check.execute(select(MCPAuditLog)).scalars().one()
            assert board_db.version == 2
            assert len(board_db.nodes) == 1
            assert record.status == "completed"
            assert record.response_json == response
            assert record.resource_version_before == 1
            assert record.resource_version_after == 2
            assert audit.status == "success"
            assert audit.request_id == "req-success"
            assert audit.client_name == "pytest-client"
            assert audit.affected_count == 1
            assert audit.version_before == 1
            assert audit.version_after == 2
            assert audit.metadata_json["summary"]["nodes_created"] == 1
            assert "token_id" not in record.response_json
            assert "request_hash" not in record.response_json

    def test_replay_returns_same_response_without_mutation(self, SessionLocal, user, token, board):
        payload = _payload(board.id, idempotency_key="patch-key-202")
        first = execute_idempotent_board_patch(
            SessionLocal,
            user_id=user.id,
            token_id=token.id,
            payload=payload,
            request_id="req-replay-1",
            scope_validator=lambda operations: None,
            board_loader=lambda db: get_owned_board(db, user.id, board.id),
        )
        with SessionLocal() as db:
            board_db = db.get(Board, board.id)
            board_db.version = 3
            db.add(
                Node(
                    id="manual-node",
                    board_id=board.id,
                    title="Otro cambio",
                    ports=[],
                    blocks=[],
                    stages=[],
                    tags=[],
                )
            )
            db.commit()

        replay = execute_idempotent_board_patch(
            SessionLocal,
            user_id=user.id,
            token_id=token.id,
            payload=payload,
            request_id="req-replay-2",
            scope_validator=lambda operations: None,
            board_loader=lambda db: get_owned_board(db, user.id, board.id),
        )
        assert replay == first
        assert replay["data"]["board_version"] == 2

        with SessionLocal() as check:
            board_db = check.get(Board, board.id)
            audits = check.execute(
                select(MCPAuditLog).order_by(MCPAuditLog.created_at.asc(), MCPAuditLog.id.asc())
            ).scalars().all()
            assert board_db.version == 3
            assert len(board_db.nodes) == 2
            assert len(audits) == 2
            assert audits[0].status == "success"
            assert audits[1].status == "replay"
            assert audits[1].request_id == "req-replay-2"
            assert audits[1].affected_count == 0
            assert audits[1].metadata_json["original_affected_count"] == 1

    def test_same_key_different_payload_conflicts(self, SessionLocal, user, token, board):
        execute_idempotent_board_patch(
            SessionLocal,
            user_id=user.id,
            token_id=token.id,
            payload=_payload(board.id, idempotency_key="patch-key-203"),
            request_id="req-conflict-1",
            scope_validator=lambda operations: None,
            board_loader=lambda db: get_owned_board(db, user.id, board.id),
        )
        with pytest.raises(IdempotencyConflict):
            execute_idempotent_board_patch(
                SessionLocal,
                user_id=user.id,
                token_id=token.id,
                payload=_payload(
                    board.id,
                    expected_version=2,
                    idempotency_key="patch-key-203",
                ),
                request_id="req-conflict-2",
                scope_validator=lambda operations: None,
                board_loader=lambda db: get_owned_board(db, user.id, board.id),
            )
        with SessionLocal() as check:
            audits = check.execute(select(MCPAuditLog)).scalars().all()
            assert len(audits) == 2
            assert sorted(item.status for item in audits) == ["error", "success"]

    def test_domain_error_removes_reservation(self, SessionLocal, user, token, board):
        payload = _payload(board.id, expected_version=99, idempotency_key="patch-key-204")
        with pytest.raises(VersionConflict):
            execute_idempotent_board_patch(
                SessionLocal,
                user_id=user.id,
                token_id=token.id,
                payload=payload,
                request_id="req-domain-error",
                scope_validator=lambda operations: None,
                board_loader=lambda db: get_owned_board(db, user.id, board.id),
            )
        with SessionLocal() as check:
            assert check.execute(select(MCPIdempotencyRecord)).scalars().all() == []
            audit = check.execute(select(MCPAuditLog)).scalars().one()
            assert audit.status == "error"
            assert audit.error_code == "VERSION_CONFLICT"
            assert audit.affected_count == 0

    def test_unexpected_error_keeps_in_progress_and_blocks_retry(self, SessionLocal, user, token, board, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(board_patches, "execute_board_patch", boom)
        payload = _payload(board.id, idempotency_key="patch-key-205")
        with pytest.raises(RuntimeError, match="boom"):
            execute_idempotent_board_patch(
                SessionLocal,
                user_id=user.id,
                token_id=token.id,
                payload=payload,
                request_id="req-internal-1",
                scope_validator=lambda operations: None,
                board_loader=lambda db: get_owned_board(db, user.id, board.id),
            )
        with SessionLocal() as check:
            record = check.execute(select(MCPIdempotencyRecord)).scalars().one()
            audit = check.execute(select(MCPAuditLog)).scalars().one()
            assert record.status == "in_progress"
            assert check.get(Board, board.id).version == 1
            assert audit.status == "error"
            assert audit.error_code == "INTERNAL_ERROR"

        with pytest.raises(IdempotencyInProgress):
            execute_idempotent_board_patch(
                SessionLocal,
                user_id=user.id,
                token_id=token.id,
                payload=payload,
                request_id="req-internal-2",
                scope_validator=lambda operations: None,
                board_loader=lambda db: get_owned_board(db, user.id, board.id),
            )

    def test_complete_failure_leaves_uncertain_in_progress(self, SessionLocal, user, token, board, monkeypatch):
        original_complete = board_patches.complete_idempotent_operation

        def broken_complete(*args, **kwargs):
            raise RuntimeError("complete failed")

        monkeypatch.setattr(board_patches, "complete_idempotent_operation", broken_complete)
        payload = _payload(board.id, idempotency_key="patch-key-206")

        with pytest.raises(RuntimeError, match="complete failed"):
            execute_idempotent_board_patch(
                SessionLocal,
                user_id=user.id,
                token_id=token.id,
                payload=payload,
                request_id="req-uncertain-1",
                scope_validator=lambda operations: None,
                board_loader=lambda db: get_owned_board(db, user.id, board.id),
            )

        monkeypatch.setattr(board_patches, "complete_idempotent_operation", original_complete)

        with SessionLocal() as check:
            board_db = check.get(Board, board.id)
            record = check.execute(select(MCPIdempotencyRecord)).scalars().one()
            audit = check.execute(select(MCPAuditLog)).scalars().one()
            assert board_db.version == 2
            assert len(board_db.nodes) == 1
            assert record.status == "in_progress"
            assert audit.status == "state_uncertain"
            assert audit.error_code == "IDEMPOTENCY_STATE_UNCERTAIN"

        with pytest.raises(IdempotencyInProgress):
            execute_idempotent_board_patch(
                SessionLocal,
                user_id=user.id,
                token_id=token.id,
                payload=payload,
                request_id="req-uncertain-2",
                scope_validator=lambda operations: None,
                board_loader=lambda db: get_owned_board(db, user.id, board.id),
            )

    def test_expired_in_progress_is_uncertain_for_apply_board_patch(self, SessionLocal, user, token, board, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(board_patches, "execute_board_patch", boom)
        payload = _payload(board.id, idempotency_key="patch-key-207")
        with pytest.raises(RuntimeError):
            execute_idempotent_board_patch(
                SessionLocal,
                user_id=user.id,
                token_id=token.id,
                payload=payload,
                request_id="req-expired-1",
                scope_validator=lambda operations: None,
                board_loader=lambda db: get_owned_board(db, user.id, board.id),
            )

        with SessionLocal() as check:
            record = check.execute(select(MCPIdempotencyRecord)).scalars().one()
            record.expires_at = record.expires_at - timedelta(minutes=10)
            check.commit()

        with pytest.raises(IdempotencyStateUncertain):
            execute_idempotent_board_patch(
                SessionLocal,
                user_id=user.id,
                token_id=token.id,
                payload=payload,
                request_id="req-expired-2",
                scope_validator=lambda operations: None,
                board_loader=lambda db: get_owned_board(db, user.id, board.id),
            )
        with SessionLocal() as check:
            audits = check.execute(select(MCPAuditLog)).scalars().all()
            assert len(audits) == 2
            assert sorted(item.status for item in audits) == ["error", "state_uncertain"]


class TestConcurrency:
    def test_same_request_only_applies_once(self, tmp_path, monkeypatch):
        db_path = tmp_path / "patch-idem-concurrency.db"
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _set_fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with SessionLocal() as db:
            user = User(
                id=uuid.uuid4().hex[:16],
                email="conc@test.com",
                name="Conc",
                auth_provider="google",
            )
            studio = Studio(
                id=uuid.uuid4().hex[:16],
                name="Studio",
                color="blue",
                user_id=user.id,
            )
            board = Board(
                id=uuid.uuid4().hex[:16],
                name="Board",
                studio_id=studio.id,
                version=1,
            )
            token = MCPToken(
                id="conc-token",
                user_id=user.id,
                name="Token",
                token_prefix="huginn_mcp_concpatch",
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                scopes=["nodes:create"],
            )
            db.add_all([user, studio, board, token])
            db.commit()
            user_id = user.id
            board_id = board.id

        original_execute = board_patches.execute_board_patch

        def slow_execute(*args, **kwargs):
            time.sleep(0.05)
            return original_execute(*args, **kwargs)

        monkeypatch.setattr(board_patches, "execute_board_patch", slow_execute)

        barrier = threading.Barrier(2)
        results: list[dict] = []
        failures: list[type[Exception]] = []

        def worker(payload):
            try:
                barrier.wait()
                results.append(
                    execute_idempotent_board_patch(
                        SessionLocal,
                        user_id=user_id,
                        token_id="conc-token",
                        payload=payload,
                        request_id=f"req-conc-{len(results) + len(failures)}",
                        scope_validator=lambda operations: None,
                        board_loader=lambda db: get_owned_board(db, user_id, board_id),
                    )
                )
            except Exception as exc:
                failures.append(type(exc))

        payload = _payload(board_id, idempotency_key="patch-key-301")
        thread_a = threading.Thread(target=worker, args=(payload,))
        thread_b = threading.Thread(target=worker, args=(payload,))
        thread_a.start()
        thread_b.start()
        thread_a.join()
        thread_b.join()

        assert len(results) == 1
        assert failures == [IdempotencyInProgress]

        with SessionLocal() as check:
            board_db = check.get(Board, board_id)
            records = check.execute(select(MCPIdempotencyRecord)).scalars().all()
            audits = check.execute(select(MCPAuditLog)).scalars().all()
            assert board_db.version == 2
            assert len(board_db.nodes) == 1
            assert len(records) == 1
            assert len(audits) == 2
            assert sorted(item.status for item in audits) == ["error", "success"]
            assert any(item.error_code == "IDEMPOTENCY_IN_PROGRESS" for item in audits)

        replay = execute_idempotent_board_patch(
            SessionLocal,
            user_id=user_id,
            token_id="conc-token",
            payload=payload,
            request_id="req-conc-replay",
            scope_validator=lambda operations: None,
            board_loader=lambda db: get_owned_board(db, user_id, board_id),
        )
        assert replay["ok"] is True
        with SessionLocal() as check:
            audits = check.execute(select(MCPAuditLog)).scalars().all()
            assert len(audits) == 3
            assert any(item.status == "replay" for item in audits)

    def test_same_key_different_payload_conflicts_concurrently(self, tmp_path, monkeypatch):
        db_path = tmp_path / "patch-idem-concurrency-conflict.db"
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _set_fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        with SessionLocal() as db:
            user = User(
                id=uuid.uuid4().hex[:16],
                email="conf@test.com",
                name="Conf",
                auth_provider="google",
            )
            studio = Studio(
                id=uuid.uuid4().hex[:16],
                name="Studio",
                color="blue",
                user_id=user.id,
            )
            board = Board(
                id=uuid.uuid4().hex[:16],
                name="Board",
                studio_id=studio.id,
                version=1,
            )
            token = MCPToken(
                id="conc-token-2",
                user_id=user.id,
                name="Token",
                token_prefix="huginn_mcp_concpatch2",
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                scopes=["nodes:create"],
            )
            db.add_all([user, studio, board, token])
            db.commit()
            user_id = user.id
            board_id = board.id

        original_execute = board_patches.execute_board_patch

        def slow_execute(*args, **kwargs):
            time.sleep(0.05)
            return original_execute(*args, **kwargs)

        monkeypatch.setattr(board_patches, "execute_board_patch", slow_execute)

        barrier = threading.Barrier(2)
        results: list[dict] = []
        failures: list[type[Exception]] = []

        def worker(payload):
            try:
                barrier.wait()
                results.append(
                    execute_idempotent_board_patch(
                        SessionLocal,
                        user_id=user_id,
                        token_id="conc-token-2",
                        payload=payload,
                        request_id=f"req-conf-conc-{len(results) + len(failures)}",
                        scope_validator=lambda operations: None,
                        board_loader=lambda db: get_owned_board(db, user_id, board_id),
                    )
                )
            except Exception as exc:
                failures.append(type(exc))

        thread_a = threading.Thread(
            target=worker,
            args=(_payload(board_id, idempotency_key="patch-key-302"),),
        )
        thread_b = threading.Thread(
            target=worker,
            args=(
                BoardPatchPayload(
                    board_id=board_id,
                    expected_version=1,
                    dry_run=False,
                    idempotency_key="patch-key-302",
                    operations=[
                        {
                            "op": "create_node",
                            "client_id": "diagnostico",
                            "node": {
                                "type": "card",
                                "title": "Otra carga",
                                "x": 100,
                                "y": 200,
                                "w": 280,
                                "ports": [],
                                "tags": [],
                                "blocks": [],
                            },
                        }
                    ],
                ),
            ),
        )
        thread_a.start()
        thread_b.start()
        thread_a.join()
        thread_b.join()

        assert len(results) == 1
        assert failures == [IdempotencyConflict]
        with SessionLocal() as check:
            audits = check.execute(select(MCPAuditLog)).scalars().all()
            assert len(audits) == 2
            assert sorted(item.status for item in audits) == ["error", "success"]
