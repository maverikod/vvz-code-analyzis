"""
Dead and orphaned search session detection.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from code_analysis.core.search_session.heartbeat import is_heartbeat_stale
from code_analysis.core.search_session.manifest import SearchSessionManifest

_PID_REUSE_TOLERANCE_SECONDS = 1.0


class DeadSessionVerdict(str, Enum):
    """Liveness classification for one search session."""

    live = "live"
    dead = "dead"
    orphaned = "orphaned"
    timed_out = "timed_out"


def evaluate_session_liveness(
    manifest: SearchSessionManifest,
    *,
    hard_timeout_seconds: float,
    now: float,
) -> DeadSessionVerdict:
    """Classify session liveness using process identity and heartbeat."""
    pid = manifest.process.main_pid
    if not _is_process_alive(pid):
        return DeadSessionVerdict.dead

    live_start = _probe_process_start_epoch(pid)
    stored_start = manifest.process.process_start_time
    if (
        live_start is not None
        and live_start > stored_start + _PID_REUSE_TOLERANCE_SECONDS
    ):
        return DeadSessionVerdict.orphaned

    if is_heartbeat_stale(
        manifest,
        hard_timeout_seconds=hard_timeout_seconds,
        now=now,
    ):
        return DeadSessionVerdict.timed_out

    return DeadSessionVerdict.live


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _probe_process_start_epoch(pid: int) -> float | None:
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.is_file():
        return None
    try:
        stat_text = stat_path.read_text(encoding="utf-8")
        rparen = stat_text.rfind(")")
        if rparen < 0:
            return None
        fields = stat_text[rparen + 2 :].split()
        if len(fields) < 20:
            return None
        starttime_ticks = int(fields[19])
        boot_time = _linux_boot_time_epoch()
        clk_tck = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        if boot_time is None or clk_tck <= 0:
            return None
        return boot_time + (starttime_ticks / clk_tck)
    except (OSError, ValueError):
        return None


def _linux_boot_time_epoch() -> float | None:
    try:
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except OSError:
        return None
    return None
