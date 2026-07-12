"""Tests del servicio de idempotencia MCP."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import MCPIdempotencyRecord, MCPToken, Studio, User
from app.services.errors import IdempotencyConflict, IdempotencyInProgress
from app.services.errors import IdempotencyStateUncertain
from app.services.mcp_idempotency import (
    IDEMPOTENCY_STATUS_COMPLETED,
    IDEMPOTENCY_STATUS_FAILED,
    IDEMPOTENCY_STATUS_IN_PROGRESS,
    begin_idempotent_operation,
    build_idempotency_request_hash,
    complete_idempotent_operation,
    fail_idempotent_operation,
    get_idempotency_record,
    purge_expired_idempotency_records,
    resolve_idempotent_replay,
    validate_idempotency_key,
)


class _AliasedPayload(BaseModel):
    expected_version: int = Field(alias="expectedVersion")
    board_id: str = Field(alias="boardId")


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(Engine, "connect")
    def _set_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def user(db) -> User:
    item = User(
        id=uuid.uuid4().hex[:16],
        email="owner@test.com",
        name="Owner",
        auth_provider="google",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def other_user(db) -> User:
    item = User(
        id=uuid.uuid4().hex[:16],
        email="other@test.com",
        name="Other",
        auth_provider="google",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def token(db, user) -> MCPToken:
    studio = Studio(
        id=uuid.uuid4().hex[:16],
        name="Studio",
        color="blue",
        user_id=user.id,
    )
    db.add(studio)
    db.commit()

    item = MCPToken(
        id=uuid.uuid4().hex[:16],
        user_id=user.id,
        name="Primary",
        token_prefix="huginn_mcp_abc123",
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        scopes=["boards:write"],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def other_token(db, other_user) -> MCPToken:
    studio = Studio(
        id=uuid.uuid4().hex[:16],
        name="Other Studio",
        color="green",
        user_id=other_user.id,
    )
    db.add(studio)
    db.commit()

    item = MCPToken(
        id=uuid.uuid4().hex[:16],
        user_id=other_user.id,
        name="Secondary",
        token_prefix="huginn_mcp_def456",
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        scopes=["boards:write"],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@pytest.fixture()
def second_token(db, user) -> MCPToken:
    item = MCPToken(
        id=uuid.uuid4().hex[:16],
        user_id=user.id,
        name="SecondarySameUser",
        token_prefix="huginn_mcp_sameusr",
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        scopes=["boards:write"],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _payload(**overrides):
    base = {
        "board_id": "board-1",
        "expected_version": 7,
        "dry_run": False,
        "operations": [
            {"op": "create_node", "client_id": "node-a", "type": "card"},
        ],
    }
    base.update(overrides)
    return base


class TestValidateIdempotencyKey:
    @pytest.mark.parametrize(
        ("value", "message"),
        [
            (None, "idempotency_key debe ser un string"),
            ("", "idempotency_key no puede estar vacío"),
            ("   ", "idempotency_key no puede estar vacío"),
            ("short", "al menos 8 caracteres"),
            ("x" * 129, "no puede superar 128 caracteres"),
        ],
    )
    def test_rejects_invalid_values(self, value, message):
        with pytest.raises(ValueError, match=message):
            validate_idempotency_key(value)

    def test_accepts_non_uuid_strings(self):
        assert validate_idempotency_key("safe-key-123") == "safe-key-123"


class TestBuildIdempotencyRequestHash:
    def test_same_payload_same_hash(self, user, token):
        payload = _payload()
        digest_a = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=payload,
            user_id=user.id,
            token_id=token.id,
        )
        digest_b = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=dict(payload),
            user_id=user.id,
            token_id=token.id,
        )
        assert digest_a == digest_b

    def test_dict_key_order_does_not_change_hash(self, user, token):
        payload_a = {"board_id": "b1", "meta": {"b": 2, "a": 1}}
        payload_b = {"meta": {"a": 1, "b": 2}, "board_id": "b1"}
        assert build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=payload_a,
            user_id=user.id,
            token_id=token.id,
        ) == build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=payload_b,
            user_id=user.id,
            token_id=token.id,
        )

    def test_field_change_changes_hash(self, user, token):
        digest_a = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=_payload(expected_version=7),
            user_id=user.id,
            token_id=token.id,
        )
        digest_b = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=_payload(expected_version=8),
            user_id=user.id,
            token_id=token.id,
        )
        assert digest_a != digest_b

    def test_tool_change_changes_hash(self, user, token):
        payload = _payload()
        digest_a = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=payload,
            user_id=user.id,
            token_id=token.id,
        )
        digest_b = build_idempotency_request_hash(
            tool_name="create_nodes_batch",
            payload=payload,
            user_id=user.id,
            token_id=token.id,
        )
        assert digest_a != digest_b

    def test_token_change_changes_hash(self, user, token, second_token):
        payload = _payload()
        digest_a = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=payload,
            user_id=user.id,
            token_id=token.id,
        )
        digest_b = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=payload,
            user_id=user.id,
            token_id=second_token.id,
        )
        assert digest_a != digest_b

    def test_unicode_nested_none_and_list_order(self, user, token):
        payload_a = {
            "board_id": "tablero-á",
            "expected_version": None,
            "operations": [{"title": "Señal"}, {"title": "Ω"}],
        }
        payload_b = {
            "board_id": "tablero-á",
            "expected_version": None,
            "operations": [{"title": "Ω"}, {"title": "Señal"}],
        }
        digest_a = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=payload_a,
            user_id=user.id,
            token_id=token.id,
        )
        digest_b = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=payload_b,
            user_id=user.id,
            token_id=token.id,
        )
        assert digest_a != digest_b

    def test_numbers_are_stable(self, user, token):
        digest_a = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload={"x": 1, "y": 1.5},
            user_id=user.id,
            token_id=token.id,
        )
        digest_b = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload={"x": 1, "y": 1.5},
            user_id=user.id,
            token_id=token.id,
        )
        assert digest_a == digest_b

    def test_pydantic_aliases_are_normalised(self, user, token):
        digest_model = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload=_AliasedPayload(expectedVersion=7, boardId="board-1"),
            user_id=user.id,
            token_id=token.id,
        )
        digest_dict = build_idempotency_request_hash(
            tool_name="apply_board_patch",
            payload={"expectedVersion": 7, "boardId": "board-1"},
            user_id=user.id,
            token_id=token.id,
        )
        assert digest_model == digest_dict


class TestBeginIdempotentOperation:
    def test_new_reservation_creates_in_progress(self, db, user, token):
        result = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-001",
            payload=_payload(),
        )
        assert result.status == "created"
        assert result.record.status == IDEMPOTENCY_STATUS_IN_PROGRESS
        assert result.record.request_hash == result.request_hash

    def test_replay_returns_stored_response(self, db, user, token):
        first = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-002",
            payload=_payload(),
        )
        complete_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-002",
            request_hash=first.request_hash,
            response_json={"ok": True, "data": {"board_id": "board-1"}},
        )
        replay = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-002",
            payload=_payload(),
        )
        assert replay.status == "replay"
        assert replay.response_json == {"ok": True, "data": {"board_id": "board-1"}}

    def test_conflict_on_same_key_with_different_payload(self, db, user, token):
        begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-003",
            payload=_payload(expected_version=7),
        )
        with pytest.raises(IdempotencyConflict):
            begin_idempotent_operation(
                db,
                user_id=user.id,
                token_id=token.id,
                tool_name="apply_board_patch",
                idempotency_key="patch-key-003",
                payload=_payload(expected_version=8),
            )

    def test_same_key_allowed_in_different_tool(self, db, user, token):
        begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="shared-key-01",
            payload=_payload(),
        )
        second = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="create_nodes_batch",
            idempotency_key="shared-key-01",
            payload={"board_id": "board-1", "nodes": []},
        )
        assert second.status == "created"

    def test_same_key_allowed_in_different_token(self, db, user, token, second_token):
        begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="shared-key-02",
            payload=_payload(),
        )
        second = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=second_token.id,
            tool_name="apply_board_patch",
            idempotency_key="shared-key-02",
            payload=_payload(),
        )
        assert second.status == "created"

    def test_in_progress_raises(self, db, user, token):
        begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-004",
            payload=_payload(),
        )
        with pytest.raises(IdempotencyInProgress):
            begin_idempotent_operation(
                db,
                user_id=user.id,
                token_id=token.id,
                tool_name="apply_board_patch",
                idempotency_key="patch-key-004",
                payload=_payload(),
            )

    def test_completed_record_can_expire_and_be_reused_after_purge(self, db, user, token):
        started_at = MCP_NOW
        first = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-005",
            payload=_payload(),
            now=started_at,
        )
        complete_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-005",
            request_hash=first.request_hash,
            response_json={"ok": True},
            now=started_at,
        )
        purged = purge_expired_idempotency_records(
            db,
            now=started_at + timedelta(hours=25),
        )
        assert purged == 1
        reused = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-005",
            payload=_payload(expected_version=9),
            now=started_at + timedelta(hours=25),
        )
        assert reused.status == "created"

    def test_abandoned_in_progress_can_be_recovered(self, db, user, token):
        started_at = MCP_NOW
        begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-006",
            payload=_payload(),
            now=started_at,
        )
        recovered = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-006",
            payload=_payload(),
            now=started_at + timedelta(seconds=301),
        )
        assert recovered.status == "created"
        assert recovered.recovered is True

    def test_expired_in_progress_can_be_marked_uncertain(self, db, user, token):
        started_at = MCP_NOW
        begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-006b",
            payload=_payload(),
            now=started_at,
        )
        record = get_idempotency_record(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-006b",
        )
        assert record is not None
        with pytest.raises(IdempotencyStateUncertain):
            resolve_idempotent_replay(
                db,
                record=record,
                request_hash=record.request_hash,
                now=started_at + timedelta(seconds=301),
                recover_expired_in_progress=False,
            )


class TestCompleteFailAndLookup:
    def test_complete_stores_versions_and_response(self, db, user, token):
        result = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-007",
            payload=_payload(),
        )
        record = complete_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-007",
            request_hash=result.request_hash,
            response_json={"ok": True, "version": 8},
            resource_version_before=7,
            resource_version_after=8,
        )
        assert record.status == IDEMPOTENCY_STATUS_COMPLETED
        assert record.response_json == {"ok": True, "version": 8}
        assert record.resource_version_before == 7
        assert record.resource_version_after == 8

    def test_fail_without_persist_deletes_record(self, db, user, token):
        result = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-008",
            payload=_payload(),
        )
        fail_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-008",
            request_hash=result.request_hash,
        )
        assert get_idempotency_record(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-008",
        ) is None

    def test_fail_with_persist_marks_failed_and_allows_same_retry(self, db, user, token):
        result = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-009",
            payload=_payload(),
        )
        fail_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-009",
            request_hash=result.request_hash,
            error_payload={"code": "TRANSIENT"},
            persist_failure=True,
        )
        failed = get_idempotency_record(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-009",
        )
        assert failed is not None
        assert failed.status == IDEMPOTENCY_STATUS_FAILED
        retried = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-009",
            payload=_payload(),
        )
        assert retried.status == "created"
        assert retried.recovered is True

    def test_failed_record_rejects_different_payload(self, db, user, token):
        result = begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-010",
            payload=_payload(),
        )
        fail_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-010",
            request_hash=result.request_hash,
            persist_failure=True,
        )
        with pytest.raises(IdempotencyConflict):
            begin_idempotent_operation(
                db,
                user_id=user.id,
                token_id=token.id,
                tool_name="apply_board_patch",
                idempotency_key="patch-key-010",
                payload=_payload(expected_version=9),
            )

    def test_lookup_is_namespaced_by_token(self, db, user, token, second_token):
        begin_idempotent_operation(
            db,
            user_id=user.id,
            token_id=token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-011",
            payload=_payload(),
        )
        assert get_idempotency_record(
            db,
            user_id=user.id,
            token_id=second_token.id,
            tool_name="apply_board_patch",
            idempotency_key="patch-key-011",
        ) is None


MCP_NOW = datetime(2026, 7, 12, 12, 0, 0)


class TestConcurrency:
    def test_same_key_same_payload_creates_single_record(self, tmp_path, monkeypatch):
        db_path = tmp_path / "idempotency.db"
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _set_fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        session = SessionLocal()
        user = User(
            id=uuid.uuid4().hex[:16],
            email="owner@test.com",
            name="Owner",
            auth_provider="google",
        )
        session.add(user)
        session.commit()
        session.add(
            MCPToken(
                id="token-main",
                user_id=user.id,
                name="Token",
                token_prefix="huginn_mcp_conc",
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                scopes=["boards:write"],
            )
        )
        session.commit()
        user_id = user.id
        session.close()

        import app.services.mcp_idempotency as svc

        original_create = svc._create_in_progress_record

        def slow_create(*args, **kwargs):
            time.sleep(0.05)
            return original_create(*args, **kwargs)

        monkeypatch.setattr(svc, "_create_in_progress_record", slow_create)

        barrier = threading.Barrier(2)
        results: list[str] = []
        failures: list[Exception] = []

        def worker(payload):
            db = SessionLocal()
            try:
                barrier.wait()
                result = begin_idempotent_operation(
                    db,
                    user_id=user_id,
                    token_id="token-main",
                    tool_name="apply_board_patch",
                    idempotency_key="patch-key-012",
                    payload=payload,
                )
                results.append(result.status)
            except Exception as exc:  # pragma: no cover - assertion checks below
                failures.append(exc)
            finally:
                db.close()

        thread_a = threading.Thread(target=worker, args=(_payload(),))
        thread_b = threading.Thread(target=worker, args=(_payload(),))
        thread_a.start()
        thread_b.start()
        thread_a.join()
        thread_b.join()

        assert results == ["created"]
        assert len(failures) == 1
        assert isinstance(failures[0], IdempotencyInProgress)

        check = SessionLocal()
        try:
            rows = check.query(MCPToken).count()
            assert rows == 1
            records = check.execute(select(MCPIdempotencyRecord)).scalars().all()
            assert len(records) == 1
            assert records[0].status == IDEMPOTENCY_STATUS_IN_PROGRESS
        finally:
            check.close()
            engine.dispose()

    def test_same_key_different_payload_conflicts(self, tmp_path, monkeypatch):
        db_path = tmp_path / "idempotency-conflict.db"
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _set_fk(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        session = SessionLocal()
        user = User(
            id=uuid.uuid4().hex[:16],
            email="owner2@test.com",
            name="Owner2",
            auth_provider="google",
        )
        session.add(user)
        session.commit()
        session.add(
            MCPToken(
                id="token-main-2",
                user_id=user.id,
                name="Token2",
                token_prefix="huginn_mcp_conc2",
                token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                scopes=["boards:write"],
            )
        )
        session.commit()
        user_id = user.id
        session.close()

        import app.services.mcp_idempotency as svc

        original_create = svc._create_in_progress_record

        def slow_create(*args, **kwargs):
            time.sleep(0.05)
            return original_create(*args, **kwargs)

        monkeypatch.setattr(svc, "_create_in_progress_record", slow_create)

        barrier = threading.Barrier(2)
        results: list[str] = []
        failures: list[type[Exception]] = []

        def worker(payload):
            db = SessionLocal()
            try:
                barrier.wait()
                result = begin_idempotent_operation(
                    db,
                    user_id=user_id,
                    token_id="token-main-2",
                    tool_name="apply_board_patch",
                    idempotency_key="patch-key-013",
                    payload=payload,
                )
                results.append(result.status)
            except Exception as exc:  # pragma: no cover - assertion checks below
                failures.append(type(exc))
            finally:
                db.close()

        thread_a = threading.Thread(target=worker, args=(_payload(),))
        thread_b = threading.Thread(target=worker, args=(_payload(expected_version=99),))
        thread_a.start()
        thread_b.start()
        thread_a.join()
        thread_b.join()

        assert results == ["created"]
        assert failures == [IdempotencyConflict]
        engine.dispose()
