"""Rate limiting reusable para solicitudes MCP."""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from .errors import RateLimitExceeded

logger = logging.getLogger(__name__)

DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_BUCKET_TTL_SECONDS = 3600
DEFAULT_CAPABILITY_TYPE = "requests"
_PURGE_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True)
class MCPRateLimitPolicy:
    category: str
    limit: int
    window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS
    capability_type: str = DEFAULT_CAPABILITY_TYPE


@dataclass(frozen=True)
class MCPRateLimitSettings:
    enabled: bool
    bucket_ttl_seconds: int
    categories: dict[str, MCPRateLimitPolicy]

    def policy_for(self, category: str) -> MCPRateLimitPolicy:
        try:
            return self.categories[category]
        except KeyError as exc:
            raise RuntimeError(
                f"No existe configuración de rate limit para la categoría {category!r}"
            ) from exc


@dataclass(frozen=True)
class RateLimitStatus:
    remaining: int
    capacity: int
    retry_after_seconds: int
    reset_estimate: int


@dataclass(frozen=True)
class RateLimitKey:
    token_id: str
    tool_name: str
    category: str
    capability_type: str


@dataclass
class _BucketState:
    tokens: float
    updated_at: float
    last_seen_at: float


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    logger.error("Invalid MCP rate limit boolean config %s=%r", name, raw)
    raise RuntimeError(
        f"{name} debe ser un booleano válido: true/false, 1/0, yes/no u on/off"
    )


def _parse_non_negative_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        logger.error("Invalid MCP rate limit integer config %s=%r", name, raw)
        raise RuntimeError(f"{name} debe ser un entero no negativo") from exc

    if value < 0:
        logger.error("Negative MCP rate limit integer config %s=%r", name, raw)
        raise RuntimeError(f"{name} debe ser un entero no negativo")

    return value


def load_mcp_rate_limit_settings() -> MCPRateLimitSettings:
    categories = {
        "read": MCPRateLimitPolicy(
            category="read",
            limit=_parse_non_negative_int_env("MCP_RATE_LIMIT_READ_PER_MINUTE", 60),
        ),
        "write": MCPRateLimitPolicy(
            category="write",
            limit=_parse_non_negative_int_env("MCP_RATE_LIMIT_WRITE_PER_MINUTE", 30),
        ),
        "batch": MCPRateLimitPolicy(
            category="batch",
            limit=_parse_non_negative_int_env("MCP_RATE_LIMIT_BATCH_PER_MINUTE", 10),
        ),
        "patch": MCPRateLimitPolicy(
            category="patch",
            limit=_parse_non_negative_int_env("MCP_RATE_LIMIT_PATCH_PER_MINUTE", 10),
        ),
        "layout": MCPRateLimitPolicy(
            category="layout",
            limit=_parse_non_negative_int_env("MCP_RATE_LIMIT_LAYOUT_PER_MINUTE", 10),
        ),
    }
    return MCPRateLimitSettings(
        enabled=_parse_bool_env("MCP_RATE_LIMIT_ENABLED", True),
        bucket_ttl_seconds=_parse_non_negative_int_env(
            "MCP_RATE_LIMIT_BUCKET_TTL_SECONDS",
            DEFAULT_BUCKET_TTL_SECONDS,
        ),
        categories=categories,
    )


class MCPRateLimiter:
    """Token bucket thread-safe y reusable."""

    def __init__(
        self,
        settings: MCPRateLimitSettings,
        *,
        clock: Callable[[], float] | None = None,
    ):
        self.settings = settings
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._buckets: dict[RateLimitKey, _BucketState] = {}
        self._last_purge_at = self._clock()

    def check(
        self,
        *,
        token_id: str,
        tool_name: str,
        category: str,
        cost: int = 1,
        capability_type: str = DEFAULT_CAPABILITY_TYPE,
    ) -> RateLimitStatus:
        return self._evaluate(
            token_id=token_id,
            tool_name=tool_name,
            category=category,
            cost=cost,
            capability_type=capability_type,
            consume=False,
        )

    def consume(
        self,
        *,
        token_id: str,
        tool_name: str,
        category: str,
        cost: int = 1,
        capability_type: str = DEFAULT_CAPABILITY_TYPE,
    ) -> RateLimitStatus:
        return self._evaluate(
            token_id=token_id,
            tool_name=tool_name,
            category=category,
            cost=cost,
            capability_type=capability_type,
            consume=True,
        )

    def get_status(
        self,
        *,
        token_id: str,
        tool_name: str,
        category: str,
        cost: int = 1,
        capability_type: str = DEFAULT_CAPABILITY_TYPE,
    ) -> RateLimitStatus:
        return self.check(
            token_id=token_id,
            tool_name=tool_name,
            category=category,
            cost=cost,
            capability_type=capability_type,
        )

    def reset(
        self,
        *,
        token_id: str,
        tool_name: str,
        category: str,
        capability_type: str = DEFAULT_CAPABILITY_TYPE,
    ) -> None:
        key = RateLimitKey(token_id, tool_name, category, capability_type)
        with self._lock:
            self._buckets.pop(key, None)

    def purge_inactive_buckets(self, *, now: float | None = None) -> int:
        if self.settings.bucket_ttl_seconds <= 0:
            return 0

        current = self._clock() if now is None else now
        with self._lock:
            purged = self._purge_inactive_locked(current)
        if purged:
            logger.info("Purged %s inactive MCP rate limit buckets", purged)
        return purged

    @property
    def bucket_count(self) -> int:
        with self._lock:
            return len(self._buckets)

    def _evaluate(
        self,
        *,
        token_id: str,
        tool_name: str,
        category: str,
        cost: int,
        capability_type: str,
        consume: bool,
    ) -> RateLimitStatus:
        if cost <= 0:
            raise ValueError("cost debe ser un entero positivo")

        policy = self.settings.policy_for(category)
        if not self.settings.enabled or policy.limit == 0:
            return RateLimitStatus(
                remaining=0,
                capacity=policy.limit,
                retry_after_seconds=0,
                reset_estimate=0,
            )

        if cost > policy.limit:
            raise ValueError(
                f"cost={cost} supera la capacidad máxima configurada ({policy.limit})"
            )

        key = RateLimitKey(token_id, tool_name, category, capability_type)
        now = self._clock()
        with self._lock:
            self._purge_if_needed_locked(now)
            bucket = self._get_bucket_locked(key, now, policy)
            self._refill_locked(bucket, now, policy)

            remaining_before = bucket.tokens
            if remaining_before + 1e-9 < cost:
                retry_after = _seconds_until_tokens(
                    required_tokens=cost - remaining_before,
                    capacity=policy.limit,
                    window_seconds=policy.window_seconds,
                )
                status = self._build_status(bucket, policy, cost)
                if not consume:
                    return status
                logger.warning(
                    "MCP rate limit exceeded token_id=%s tool_name=%s retry_after=%s",
                    token_id,
                    tool_name,
                    retry_after,
                )
                raise RateLimitExceeded(
                    tool_name=tool_name,
                    limit=policy.limit,
                    window_seconds=policy.window_seconds,
                    retry_after_seconds=retry_after,
                )

            if consume:
                bucket.tokens = max(bucket.tokens - cost, 0.0)
                bucket.last_seen_at = now

            return self._build_status(bucket, policy, cost)

    def _get_bucket_locked(
        self,
        key: RateLimitKey,
        now: float,
        policy: MCPRateLimitPolicy,
    ) -> _BucketState:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _BucketState(
                tokens=float(policy.limit),
                updated_at=now,
                last_seen_at=now,
            )
            self._buckets[key] = bucket
        return bucket

    def _refill_locked(
        self,
        bucket: _BucketState,
        now: float,
        policy: MCPRateLimitPolicy,
    ) -> None:
        elapsed = max(now - bucket.updated_at, 0.0)
        if elapsed <= 0:
            bucket.last_seen_at = now
            return

        refill_rate = policy.limit / float(policy.window_seconds)
        bucket.tokens = min(
            float(policy.limit),
            bucket.tokens + (elapsed * refill_rate),
        )
        bucket.updated_at = now
        bucket.last_seen_at = now

    def _build_status(
        self,
        bucket: _BucketState,
        policy: MCPRateLimitPolicy,
        cost: int,
    ) -> RateLimitStatus:
        remaining = max(int(math.floor(bucket.tokens + 1e-9)), 0)
        retry_after = 0
        if bucket.tokens + 1e-9 < cost:
            retry_after = _seconds_until_tokens(
                required_tokens=cost - bucket.tokens,
                capacity=policy.limit,
                window_seconds=policy.window_seconds,
            )
        reset_estimate = _seconds_until_tokens(
            required_tokens=max(float(policy.limit) - bucket.tokens, 0.0),
            capacity=policy.limit,
            window_seconds=policy.window_seconds,
        )
        return RateLimitStatus(
            remaining=remaining,
            capacity=policy.limit,
            retry_after_seconds=retry_after,
            reset_estimate=reset_estimate,
        )

    def _purge_if_needed_locked(self, now: float) -> None:
        if (now - self._last_purge_at) < _PURGE_INTERVAL_SECONDS:
            return
        self._purge_inactive_locked(now)
        self._last_purge_at = now

    def _purge_inactive_locked(self, now: float) -> int:
        ttl = self.settings.bucket_ttl_seconds
        to_delete = [
            key
            for key, bucket in self._buckets.items()
            if (now - bucket.last_seen_at) >= ttl
        ]
        for key in to_delete:
            self._buckets.pop(key, None)
        return len(to_delete)


def _seconds_until_tokens(
    *,
    required_tokens: float,
    capacity: int,
    window_seconds: int,
) -> int:
    if required_tokens <= 0:
        return 0
    refill_rate = capacity / float(window_seconds)
    if refill_rate <= 0:
        return 0
    return max(int(math.ceil(required_tokens / refill_rate)), 0)


_default_limiter: MCPRateLimiter | None = None
_default_limiter_lock = threading.Lock()


def get_default_rate_limiter() -> MCPRateLimiter:
    global _default_limiter
    if _default_limiter is not None:
        return _default_limiter

    with _default_limiter_lock:
        if _default_limiter is None:
            _default_limiter = MCPRateLimiter(load_mcp_rate_limit_settings())
    return _default_limiter


def configure_default_rate_limiter(
    *,
    settings: MCPRateLimitSettings | None = None,
    clock: Callable[[], float] | None = None,
) -> MCPRateLimiter:
    global _default_limiter
    with _default_limiter_lock:
        _default_limiter = MCPRateLimiter(
            settings or load_mcp_rate_limit_settings(),
            clock=clock,
        )
        return _default_limiter


def clear_default_rate_limiter() -> None:
    global _default_limiter
    with _default_limiter_lock:
        _default_limiter = None


def check_rate_limit(
    *,
    token_id: str,
    tool_name: str,
    category: str,
    cost: int = 1,
    capability_type: str = DEFAULT_CAPABILITY_TYPE,
    limiter: MCPRateLimiter | None = None,
) -> RateLimitStatus:
    active_limiter = limiter or get_default_rate_limiter()
    return active_limiter.check(
        token_id=token_id,
        tool_name=tool_name,
        category=category,
        cost=cost,
        capability_type=capability_type,
    )


def consume_rate_limit(
    *,
    token_id: str,
    tool_name: str,
    category: str,
    cost: int = 1,
    capability_type: str = DEFAULT_CAPABILITY_TYPE,
    limiter: MCPRateLimiter | None = None,
) -> RateLimitStatus:
    active_limiter = limiter or get_default_rate_limiter()
    return active_limiter.consume(
        token_id=token_id,
        tool_name=tool_name,
        category=category,
        cost=cost,
        capability_type=capability_type,
    )


def get_rate_limit_status(
    *,
    token_id: str,
    tool_name: str,
    category: str,
    cost: int = 1,
    capability_type: str = DEFAULT_CAPABILITY_TYPE,
    limiter: MCPRateLimiter | None = None,
) -> RateLimitStatus:
    active_limiter = limiter or get_default_rate_limiter()
    return active_limiter.get_status(
        token_id=token_id,
        tool_name=tool_name,
        category=category,
        cost=cost,
        capability_type=capability_type,
    )


def reset_rate_limit(
    *,
    token_id: str,
    tool_name: str,
    category: str,
    capability_type: str = DEFAULT_CAPABILITY_TYPE,
    limiter: MCPRateLimiter | None = None,
) -> None:
    active_limiter = limiter or get_default_rate_limiter()
    active_limiter.reset(
        token_id=token_id,
        tool_name=tool_name,
        category=category,
        capability_type=capability_type,
    )


def purge_inactive_rate_limit_buckets(
    *,
    limiter: MCPRateLimiter | None = None,
    now: float | None = None,
) -> int:
    active_limiter = limiter or get_default_rate_limiter()
    return active_limiter.purge_inactive_buckets(now=now)
