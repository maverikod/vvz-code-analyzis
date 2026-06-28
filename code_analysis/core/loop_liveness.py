"""
Main event-loop liveness beacon.

A lightweight coroutine running on the main server loop calls :func:`beat`
periodically. An independent watchdog thread reads :func:`seconds_since_beat`
to distinguish "loop alive but busy" (beat refreshed between short tasks) from
"loop wedged" (beat goes stale because a blocking call parked the loop thread).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import time

# Default cadence of the main-loop beat coroutine (seconds).
LOOP_BEAT_INTERVAL: float = 5.0

_last_beat: float = time.monotonic()
_ever_beat: bool = False


def beat() -> None:
    """Record that the main loop is alive (called from the main loop)."""
    global _last_beat, _ever_beat
    _last_beat = time.monotonic()
    _ever_beat = True


def has_beaten() -> bool:
    """Return True once the main-loop beat coroutine has run at least once.

    The watchdog uses this to avoid false stall reports during startup, before
    the beat coroutine is scheduled (DB open can take tens of seconds).
    """
    return _ever_beat


def seconds_since_beat() -> float:
    """Return seconds since the last main-loop beat (read from any thread)."""
    return time.monotonic() - _last_beat


async def loop_liveness_beat_loop(interval: float = LOOP_BEAT_INTERVAL) -> None:
    """Refresh the liveness beacon on the main loop until cancelled."""
    while True:
        beat()
        await asyncio.sleep(interval)
