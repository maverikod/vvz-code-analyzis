"""
Server manager CLI for running `code-analysis-server` as a daemon.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


DEFAULT_SHUTDOWN_GRACE_SECONDS = 10.0


def _default_pidfile_path(config_path: str) -> Path:
    """
    Build default pidfile path based on the config location.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Path to pidfile.
    """

    cfg = Path(config_path).resolve()
    return cfg.parent / ".code-analysis-server.pid"


def _read_shutdown_grace_seconds(config_path: str) -> float:
    """
    Read shutdown grace period from config.

    Used as the maximum time to wait after sending SIGTERM before escalating to SIGKILL.

    Supported config locations (first found wins):
    - process_management.shutdown_grace_seconds
    - server_manager.shutdown_grace_seconds

    Args:
        config_path: Path to config.json.

    Returns:
        Grace period in seconds.
    """

    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_SHUTDOWN_GRACE_SECONDS

    for section_name in ("process_management", "server_manager"):
        section = cfg.get(section_name)
        if isinstance(section, dict):
            val = section.get("shutdown_grace_seconds")
            if isinstance(val, (int, float)) and float(val) > 0:
                return float(val)
    return DEFAULT_SHUTDOWN_GRACE_SECONDS


def _read_pid(pidfile: Path) -> Optional[int]:
    """
    Read pid from pidfile.

    Args:
        pidfile: Path to pidfile.

    Returns:
        PID if pidfile exists and contains an integer, otherwise None.
    """

    try:
        return int(pidfile.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _is_alive(pid: int) -> bool:
    """
    Check if a PID exists.

    Args:
        pid: Process id.

    Returns:
        True if process exists, False otherwise.
    """

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # If we don't have permission to signal it, it's still alive.
        return True


def _kill_process_group(pid: int, timeout_s: float) -> None:
    """
    Terminate process group with SIGTERM, then SIGKILL if needed.

    The server spawns child processes (workers). Hung children can keep resources
    (e.g. port 15000) busy even if the parent receives SIGTERM, so we must
    terminate the whole process group.

    Args:
        pid: Process id.
        timeout_s: How long to wait after SIGTERM before SIGKILL.

    Returns:
        None.
    """

    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    except Exception:
        pgid = None

    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _is_alive(pid):
            return
        time.sleep(0.2)

    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _find_daemon_pids(config_path: str) -> list[int]:
    """
    Best-effort: find running daemon PIDs for this config.

    Args:
        config_path: Path to config.json.

    Returns:
        List of matching PIDs.
    """

    # We cannot rely on exact string match because the running process may have
    # `--config config.json` (relative) while our config_path can be absolute.
    #
    # Use `ps` output and parse argv as a robust fallback.
    cfg_resolved = str(Path(config_path).resolve())
    cfg_basename = Path(config_path).name

    try:
        out = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True)
    except Exception:
        return []

    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid_str, args_str = line.split(maxsplit=1)
            pid = int(pid_str)
        except Exception:
            continue

        if "-m code_analysis.main" not in args_str:
            continue
        if "--daemon" not in args_str:
            continue
        if "--config" not in args_str:
            continue

        parts = args_str.split()
        try:
            cfg_idx = parts.index("--config")
            cfg_val = parts[cfg_idx + 1]
        except Exception:
            continue

        if cfg_val == config_path or cfg_val == cfg_resolved:
            pids.append(pid)
            continue

        # Accept basename match as a last resort (common case: `config.json`)
        if Path(cfg_val).name == cfg_basename:
            pids.append(pid)
            continue

    return sorted(set(pids))


def _spawn_daemon(config_path: str, pidfile: Path) -> int:
    """
    Spawn daemon server process.

    Args:
        config_path: Path to config JSON.
        pidfile: Path to pidfile to write.

    Returns:
        PID of spawned process.
    """

    python = sys.executable
    args = [python, "-m", "code_analysis.main", "--config", config_path, "--daemon"]
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    pidfile.write_text(str(proc.pid), encoding="utf-8")
    return proc.pid


def _cmd_status(config_path: str) -> int:
    """
    Print daemon status.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    pidfile = _default_pidfile_path(config_path)
    pid = _read_pid(pidfile)
    if pid is None:
        print("stopped")
        return 0
    if _is_alive(pid):
        print(f"running pid={pid}")
        return 0
    print("stopped (stale pidfile)")
    return 0


def _cmd_stop(config_path: str) -> int:
    """
    Stop daemon process.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    grace = _read_shutdown_grace_seconds(config_path)
    pidfile = _default_pidfile_path(config_path)
    pid = _read_pid(pidfile)

    # Prefer pidfile, but also kill any matching daemons (stale pidfiles happen).
    pids: list[int] = []
    if pid is not None:
        pids.append(pid)
    pids.extend([p for p in _find_daemon_pids(config_path) if p not in pids])

    if not pids:
        return 0

    for p in pids:
        _kill_process_group(p, timeout_s=grace)

    try:
        pidfile.unlink(missing_ok=True)
    except Exception:
        # Best effort cleanup; stale pidfile is handled by status/start.
        pass
    return 0


def _cmd_start(config_path: str) -> int:
    """
    Start daemon process (if not already running).

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    pidfile = _default_pidfile_path(config_path)
    pid = _read_pid(pidfile)
    if pid is not None and _is_alive(pid):
        print(f"already running pid={pid}")
        return 0
    # stale pidfile
    try:
        pidfile.unlink(missing_ok=True)
    except Exception:
        pass

    new_pid = _spawn_daemon(config_path, pidfile)
    print(f"started pid={new_pid}")
    return 0


def _cmd_restart(config_path: str) -> int:
    """
    Restart daemon process.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    _cmd_stop(config_path)
    return _cmd_start(config_path)


def server(argv: Optional[list[str]] = None) -> int:
    """
    Console entrypoint for `code-analysis-server`.

    Args:
        argv: Optional argv override.

    Returns:
        Exit code.
    """

    parser = argparse.ArgumentParser(prog="code-analysis-server")
    parser.add_argument("--config", required=True, help="Path to config.json")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("restart")
    sub.add_parser("status")
    ns = parser.parse_args(argv)

    if ns.cmd == "start":
        return _cmd_start(ns.config)
    if ns.cmd == "stop":
        return _cmd_stop(ns.config)
    if ns.cmd == "restart":
        return _cmd_restart(ns.config)
    if ns.cmd == "status":
        return _cmd_status(ns.config)

    raise RuntimeError(f"Unknown command: {ns.cmd}")


if __name__ == "__main__":
    raise SystemExit(server())


