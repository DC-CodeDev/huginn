from __future__ import annotations

import threading

import pytest

from app.services.errors import RateLimitExceeded
from app.services.mcp_rate_limit import (
    MCPRateLimiter,
    MCPRateLimitPolicy,
    MCPRateLimitSettings,
    check_rate_limit,
    clear_default_rate_limiter,
    configure_default_rate_limiter,
    consume_rate_limit,
    get_rate_limit_status,
    load_mcp_rate_limit_settings,
    purge_inactive_rate_limit_buckets,
    reset_rate_limit,
)


class FakeClock:
    def __init__(self, start: float = 0.0):
        self._value = start
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self._value

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._value += seconds


def _settings(
    *,
    enabled: bool = True,
    patch_limit: int = 10,
    bucket_ttl_seconds: int = 3600,
) -> MCPRateLimitSettings:
    return MCPRateLimitSettings(
        enabled=enabled,
        bucket_ttl_seconds=bucket_ttl_seconds,
        categories={
            "read": MCPRateLimitPolicy(category="read", limit=60),
            "write": MCPRateLimitPolicy(category="write", limit=30),
            "batch": MCPRateLimitPolicy(category="batch", limit=10),
            "patch": MCPRateLimitPolicy(category="patch", limit=patch_limit),
            "layout": MCPRateLimitPolicy(category="layout", limit=10),
        },
    )


@pytest.fixture(autouse=True)
def _reset_default_limiter():
    clear_default_rate_limiter()
    yield
    clear_default_rate_limiter()


class TestLoadMCPRateLimitSettings:
    def test_defaults(self, monkeypatch):
        for name in (
            "MCP_RATE_LIMIT_ENABLED",
            "MCP_RATE_LIMIT_READ_PER_MINUTE",
            "MCP_RATE_LIMIT_WRITE_PER_MINUTE",
            "MCP_RATE_LIMIT_BATCH_PER_MINUTE",
            "MCP_RATE_LIMIT_PATCH_PER_MINUTE",
            "MCP_RATE_LIMIT_LAYOUT_PER_MINUTE",
            "MCP_RATE_LIMIT_BUCKET_TTL_SECONDS",
        ):
            monkeypatch.delenv(name, raising=False)

        settings = load_mcp_rate_limit_settings()

        assert settings.enabled is True
        assert settings.bucket_ttl_seconds == 3600
        assert settings.policy_for("read").limit == 60
        assert settings.policy_for("write").limit == 30
        assert settings.policy_for("batch").limit == 10
        assert settings.policy_for("patch").limit == 10
        assert settings.policy_for("layout").limit == 10

    def test_custom_values(self, monkeypatch):
        monkeypatch.setenv("MCP_RATE_LIMIT_ENABLED", "false")
        monkeypatch.setenv("MCP_RATE_LIMIT_READ_PER_MINUTE", "11")
        monkeypatch.setenv("MCP_RATE_LIMIT_WRITE_PER_MINUTE", "12")
        monkeypatch.setenv("MCP_RATE_LIMIT_BATCH_PER_MINUTE", "13")
        monkeypatch.setenv("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "14")
        monkeypatch.setenv("MCP_RATE_LIMIT_LAYOUT_PER_MINUTE", "15")
        monkeypatch.setenv("MCP_RATE_LIMIT_BUCKET_TTL_SECONDS", "99")

        settings = load_mcp_rate_limit_settings()

        assert settings.enabled is False
        assert settings.bucket_ttl_seconds == 99
        assert settings.policy_for("read").limit == 11
        assert settings.policy_for("write").limit == 12
        assert settings.policy_for("batch").limit == 13
        assert settings.policy_for("patch").limit == 14
        assert settings.policy_for("layout").limit == 15

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("MCP_RATE_LIMIT_ENABLED", "maybe"),
            ("MCP_RATE_LIMIT_READ_PER_MINUTE", "abc"),
            ("MCP_RATE_LIMIT_WRITE_PER_MINUTE", "-1"),
            ("MCP_RATE_LIMIT_BATCH_PER_MINUTE", ""),
            ("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "-10"),
            ("MCP_RATE_LIMIT_LAYOUT_PER_MINUTE", "1.5"),
            ("MCP_RATE_LIMIT_BUCKET_TTL_SECONDS", "-5"),
        ],
    )
    def test_invalid_values_raise_clear_error(self, monkeypatch, name, value):
        monkeypatch.setenv(name, value)
        with pytest.raises(RuntimeError):
            load_mcp_rate_limit_settings()

    def test_zero_limit_is_allowed_and_disables_that_category(self, monkeypatch):
        monkeypatch.setenv("MCP_RATE_LIMIT_PATCH_PER_MINUTE", "0")
        settings = load_mcp_rate_limit_settings()
        assert settings.policy_for("patch").limit == 0

    def test_boolean_enabled_accepts_common_false_values(self, monkeypatch):
        monkeypatch.setenv("MCP_RATE_LIMIT_ENABLED", "0")
        settings = load_mcp_rate_limit_settings()
        assert settings.enabled is False


class TestMCPRateLimiterAlgorithm:
    def test_new_bucket_starts_full(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=3), clock=clock)

        status = get_rate_limit_status(
            token_id="token-1",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        assert status.capacity == 3
        assert status.remaining == 3
        assert status.retry_after_seconds == 0
        assert status.reset_estimate == 0

    def test_consumption_and_exhaustion(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=2), clock=clock)

        first = consume_rate_limit(
            token_id="token-1",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )
        second = consume_rate_limit(
            token_id="token-1",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        assert first.remaining == 1
        assert second.remaining == 0
        with pytest.raises(RateLimitExceeded) as exc:
            consume_rate_limit(
                token_id="token-1",
                tool_name="apply_board_patch",
                category="patch",
                limiter=limiter,
            )
        assert exc.value.retry_after_seconds == 30

    def test_partial_refill(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=2), clock=clock)
        consume_rate_limit(
            token_id="token-1",
            tool_name="apply_board_patch",
            category="patch",
            cost=2,
            limiter=limiter,
        )

        clock.advance(15)
        status = get_rate_limit_status(
            token_id="token-1",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        assert status.remaining == 0
        assert status.retry_after_seconds == 15
        assert status.reset_estimate == 45

    def test_full_refill_caps_at_capacity(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=2), clock=clock)
        consume_rate_limit(
            token_id="token-1",
            tool_name="apply_board_patch",
            category="patch",
            cost=2,
            limiter=limiter,
        )

        clock.advance(120)
        status = get_rate_limit_status(
            token_id="token-1",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        assert status.remaining == 2
        assert status.reset_estimate == 0

    def test_cost_greater_than_one(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=5), clock=clock)

        status = consume_rate_limit(
            token_id="token-1",
            tool_name="apply_board_patch",
            category="patch",
            cost=3,
            limiter=limiter,
        )

        assert status.remaining == 2

    def test_retry_after_rounds_up(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=3), clock=clock)
        consume_rate_limit(
            token_id="token-1",
            tool_name="apply_board_patch",
            category="patch",
            cost=3,
            limiter=limiter,
        )

        clock.advance(5)
        with pytest.raises(RateLimitExceeded) as exc:
            consume_rate_limit(
                token_id="token-1",
                tool_name="apply_board_patch",
                category="patch",
                cost=1,
                limiter=limiter,
            )

        assert exc.value.retry_after_seconds == 15

    def test_keys_are_isolated_by_token(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=1), clock=clock)

        consume_rate_limit(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )
        status = get_rate_limit_status(
            token_id="token-b",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        assert status.remaining == 1

    def test_keys_are_isolated_by_category_and_tool(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=1), clock=clock)

        consume_rate_limit(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )
        patch_status = get_rate_limit_status(
            token_id="token-a",
            tool_name="other_tool",
            category="patch",
            limiter=limiter,
        )
        read_status = get_rate_limit_status(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="read",
            limiter=limiter,
        )

        assert patch_status.remaining == 1
        assert read_status.remaining == 60

    def test_disabled_global_feature_allows_requests_without_buckets(self):
        limiter = MCPRateLimiter(_settings(enabled=False, patch_limit=1))
        status = consume_rate_limit(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        assert status.capacity == 1
        assert limiter.bucket_count == 0

    def test_zero_limit_category_allows_requests_without_buckets(self):
        limiter = MCPRateLimiter(_settings(patch_limit=0))
        status = consume_rate_limit(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        assert status.capacity == 0
        assert limiter.bucket_count == 0

    def test_cleanup_purges_inactive_buckets(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=1, bucket_ttl_seconds=10), clock=clock)
        consume_rate_limit(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        clock.advance(11)
        purged = purge_inactive_rate_limit_buckets(limiter=limiter, now=clock())

        assert purged == 1
        assert limiter.bucket_count == 0

    def test_reset_clears_specific_bucket(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=1), clock=clock)
        consume_rate_limit(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        reset_rate_limit(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )
        status = get_rate_limit_status(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        assert status.remaining == 1

    def test_check_does_not_consume(self):
        clock = FakeClock()
        limiter = MCPRateLimiter(_settings(patch_limit=2), clock=clock)

        first = check_rate_limit(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )
        second = consume_rate_limit(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )

        assert first.remaining == 2
        assert second.remaining == 1


class TestMCPRateLimiterConcurrency:
    def test_two_requests_compete_for_last_token(self):
        limiter = MCPRateLimiter(_settings(patch_limit=1), clock=FakeClock())
        barrier = threading.Barrier(2)
        results: list[str] = []
        errors: list[RateLimitExceeded] = []

        def worker():
            try:
                barrier.wait()
                consume_rate_limit(
                    token_id="token-a",
                    tool_name="apply_board_patch",
                    category="patch",
                    limiter=limiter,
                )
                results.append("ok")
            except RateLimitExceeded as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(results) == 1
        assert len(errors) == 1
        assert errors[0].retry_after_seconds == 60

    def test_many_concurrent_requests_never_go_negative(self):
        limiter = MCPRateLimiter(_settings(patch_limit=10), clock=FakeClock())
        barrier = threading.Barrier(20)
        successes = 0
        failures = 0
        lock = threading.Lock()

        def worker():
            nonlocal successes, failures
            try:
                barrier.wait()
                consume_rate_limit(
                    token_id="token-a",
                    tool_name="apply_board_patch",
                    category="patch",
                    limiter=limiter,
                )
                with lock:
                    successes += 1
            except RateLimitExceeded:
                with lock:
                    failures += 1

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        status = get_rate_limit_status(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
            limiter=limiter,
        )
        assert successes == 10
        assert failures == 10
        assert status.remaining == 0

    def test_concurrency_isolated_by_token(self):
        limiter = MCPRateLimiter(_settings(patch_limit=1), clock=FakeClock())
        barrier = threading.Barrier(2)
        results: list[str] = []

        def worker(token_id: str):
            barrier.wait()
            consume_rate_limit(
                token_id=token_id,
                tool_name="apply_board_patch",
                category="patch",
                limiter=limiter,
            )
            results.append(token_id)

        threads = [
            threading.Thread(target=worker, args=("token-a",)),
            threading.Thread(target=worker, args=("token-b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(results) == ["token-a", "token-b"]

    def test_concurrency_isolated_by_tool(self):
        limiter = MCPRateLimiter(_settings(patch_limit=1), clock=FakeClock())
        barrier = threading.Barrier(2)
        results: list[str] = []

        def worker(tool_name: str):
            barrier.wait()
            consume_rate_limit(
                token_id="token-a",
                tool_name=tool_name,
                category="patch",
                limiter=limiter,
            )
            results.append(tool_name)

        threads = [
            threading.Thread(target=worker, args=("apply_board_patch",)),
            threading.Thread(target=worker, args=("other_tool",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sorted(results) == ["apply_board_patch", "other_tool"]


class TestDefaultLimiterWrappers:
    def test_default_wrappers_support_fake_clock(self):
        clock = FakeClock()
        configure_default_rate_limiter(settings=_settings(patch_limit=1), clock=clock)

        status = consume_rate_limit(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
        )
        assert status.remaining == 0

        clock.advance(60)
        status = get_rate_limit_status(
            token_id="token-a",
            tool_name="apply_board_patch",
            category="patch",
        )
        assert status.remaining == 1
