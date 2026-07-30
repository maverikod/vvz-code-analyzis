"""
Session TTL policy and maximum block size configuration.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from code_analysis.core.constants import (
    DEFAULT_SEARCH_SESSION_SWEEP_INTERVAL_SECONDS,
    DEFAULT_SEARCH_SESSION_TTL_SECONDS,
    SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MAX,
    SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MIN,
)

# Re-exported under the historical names used across config_generator.py,
# config_validator/, and their tests -- the constants themselves now live in
# core/constants.py next to the project's other timeout/interval defaults
# (single source of truth); these names stay stable so existing imports keep
# working.
SEARCH_SESSION_TTL_SECONDS_DEFAULT = DEFAULT_SEARCH_SESSION_TTL_SECONDS
SEARCH_MAX_BLOCK_SIZE_BYTES_DEFAULT = 4_096
SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_DEFAULT = (
    DEFAULT_SEARCH_SESSION_SWEEP_INTERVAL_SECONDS
)

TTL_SECONDS_MIN = 60
TTL_SECONDS_MAX = 604_800
MAX_BLOCK_SIZE_BYTES_MIN = 1024
MAX_BLOCK_SIZE_BYTES_MAX = 16_777_216
SWEEP_INTERVAL_SECONDS_MIN = SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MIN
SWEEP_INTERVAL_SECONDS_MAX = SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_MAX


@dataclass(frozen=True)
class SessionTTLPolicy:
    """Validated search session TTL, result block size, and sweep cadence.

    Attributes:
        ttl_seconds: How long an idle (last-access), terminal-state session
            directory is retained before it becomes eligible for cleanup.
            Config: code_analysis.search_session.ttl_seconds. Constant
            default: DEFAULT_SEARCH_SESSION_TTL_SECONDS.
        max_block_size_bytes: Max bytes per published result block.
        sweep_interval_seconds: Cadence of the periodic background sweep
            that removes expired session directories. Config:
            code_analysis.search_session.poll_interval. Constant default:
            DEFAULT_SEARCH_SESSION_SWEEP_INTERVAL_SECONDS.
    """

    ttl_seconds: int
    max_block_size_bytes: int
    sweep_interval_seconds: int = SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_DEFAULT


def load_session_ttl_policy(config_data: dict[str, Any]) -> SessionTTLPolicy:
    """Load policy from ``code_analysis.search_session`` or top-level ``search_session``."""
    code_analysis = config_data.get("code_analysis") or {}
    search_session = (
        code_analysis.get("search_session") or config_data.get("search_session") or {}
    )
    ttl_raw = search_session.get("ttl_seconds", SEARCH_SESSION_TTL_SECONDS_DEFAULT)
    block_raw = search_session.get(
        "max_block_size_bytes",
        SEARCH_MAX_BLOCK_SIZE_BYTES_DEFAULT,
    )
    sweep_raw = search_session.get(
        "poll_interval",
        SEARCH_SESSION_SWEEP_INTERVAL_SECONDS_DEFAULT,
    )
    return SessionTTLPolicy(
        ttl_seconds=int(ttl_raw),
        max_block_size_bytes=int(block_raw),
        sweep_interval_seconds=int(sweep_raw),
    )


def validate_session_ttl_policy(policy: SessionTTLPolicy) -> None:
    """Raise ValueError when TTL, block size, or sweep interval is invalid or out of range."""
    _validate_positive_int(
        policy.ttl_seconds,
        name="ttl_seconds",
        minimum=TTL_SECONDS_MIN,
        maximum=TTL_SECONDS_MAX,
    )
    _validate_positive_int(
        policy.max_block_size_bytes,
        name="max_block_size_bytes",
        minimum=MAX_BLOCK_SIZE_BYTES_MIN,
        maximum=MAX_BLOCK_SIZE_BYTES_MAX,
    )
    _validate_positive_int(
        policy.sweep_interval_seconds,
        name="poll_interval",
        minimum=SWEEP_INTERVAL_SECONDS_MIN,
        maximum=SWEEP_INTERVAL_SECONDS_MAX,
    )


def _validate_positive_int(
    value: object,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> None:
    """Return validate positive int."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be int, got {type(value).__name__}")
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}, got {value}")
