"""
Transient failure classification and retry policy for database client.

Implements approved policy from cst_save_tree RPC stability task: transient
categories (rpc_connect_refused, sqlite_db_locked), retry budget, and delay
curve. Used by save path and RPC call sites to retry only on transient errors.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import errno
import random

# --- Retry budget (fixed; no "tune later") ---
MAX_ATTEMPTS = 4  # 1 initial + 3 retries
INITIAL_DELAY_SECONDS = 0.2
BACKOFF_MULTIPLIER = 2.0
MAX_DELAY_SECONDS = 1.0
JITTER_FRACTION = 0.05  # ±5%
MAX_TOTAL_ELAPSED_SECONDS = 5.0

# Transient category codes (for logging)
CATEGORY_RPC_CONNECT_REFUSED = "rpc_connect_refused"
CATEGORY_SQLITE_DB_LOCKED = "sqlite_db_locked"


def is_rpc_connect_refused(exc: BaseException) -> bool:
    """Return True if the exception indicates transient RPC connection refused.

    Matches: ConnectionRefusedError, or ConnectionError (from this package)
    with cause/errno indicating connection refused (e.g. Errno 111).
    Detected at RPCClient._create_connection / _send_request.

    Args:
        exc: Exception to classify.

    Returns:
        True if transient connect-refused, False otherwise.
    """
    if isinstance(exc, ConnectionRefusedError):
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and getattr(cause, "errno", None) == errno.ECONNREFUSED:
        return True
    msg = str(exc).lower()
    if "connection refused" in msg or "errno 111" in msg or ": 111]" in msg:
        return True
    return False


def is_sqlite_db_locked(error_message: str) -> bool:
    """Return True if the error message indicates transient SQLite lock.

    Matches messages from driver (execute_batch, SQLiteOperations.update) or
    RPC ErrorResult: "database is locked", "database is locked (BUSY)",
    "execute_batch failed: database is locked", "Failed to update rows: database is locked".
    Non-lock SQL errors (FK, schema, etc.) must not match and must fail fast.

    Args:
        error_message: Error string from result or exception.

    Returns:
        True if transient DB lock, False otherwise.
    """
    if not error_message:
        return False
    msg = error_message.lower()
    return "database is locked" in msg or "database is busy" in msg


def compute_retry_delay(attempt_1based: int) -> float:
    """Compute delay in seconds before the next retry attempt.

    Delay curve: initial_delay * (backoff ** (attempt_1based - 1)), capped
    by max_delay, then ± jitter (5%).

    Args:
        attempt_1based: 1-based attempt index (1 = first retry, 2 = second, ...).

    Returns:
        Delay in seconds (>= 0).
    """
    raw = INITIAL_DELAY_SECONDS * (BACKOFF_MULTIPLIER ** (attempt_1based - 1))
    capped = min(raw, MAX_DELAY_SECONDS)
    jitter = capped * JITTER_FRACTION * (2 * random.random() - 1)
    return max(0.0, capped + jitter)


def format_retry_summary_suffix(attempts: int, elapsed_sec: float) -> str:
    """Format retry summary for appending to error message (contract: no new keys).

    Args:
        attempts: Total number of attempts made.
        elapsed_sec: Total elapsed seconds.

    Returns:
        Suffix string, e.g. ' (after 4 attempts, 1.4s total)'.
    """
    return f" (after {attempts} attempts, {elapsed_sec:.1f}s total)"
