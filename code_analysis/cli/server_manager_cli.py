"""
Server manager CLI for running `code-analysis-server` as a daemon.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import argparse
import io
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from code_analysis.core.client_sessions import (
    count_session_file_locks,
    list_client_sessions,
    list_locked_files,
)
from code_analysis.core.database_client.factory import (
    create_database_client_from_config_path,
)

# For stderr redirect: DEVNULL (int) or open file (TextIO)
_StderrDest = Union[int, io.TextIOWrapper]


DEFAULT_SHUTDOWN_GRACE_SECONDS = 10.0

# Stop/restart: re-scan processes so slow children and races do not leave duplicates;
# cap rounds so a wedged host still returns.
_STOP_MAX_ROUNDS = 30
_STOP_ROUND_DELAY_S = 0.2
# Brief pause after last PID disappears so listen sockets / workers can release.
_RESTART_SETTLE_S = 0.35

# Override for tests or exotic layouts (must be an existing executable).
_ENV_DAEMON_PYTHON = "CODE_ANALYSIS_DAEMON_PYTHON"

# Config discovery for ``casmgr`` (see ``_resolve_config_path``).
_ENV_CASMGR_CONFIG = "CASMGR_CONFIG"
_SYSTEM_DEFAULT_CONFIG = Path("/etc/casmgr/config.json")
_CWD_CONFIG_NAME = "config.json"


def _resolve_config_path(cli_config: Optional[str]) -> Optional[str]:
    """
    Resolve ``config.json`` path by priority:

    1. ``--config`` from the CLI (must exist).
    2. ``CASMGR_CONFIG`` (must exist if set).
    3. ``/etc/casmgr/config.json`` if present.
    4. ``./config.json`` under the current working directory if present.

    Returns:
        Absolute path to an existing config file, or ``None`` if none found
        (caller should print the error already emitted here).
    """

    if cli_config is not None and str(cli_config).strip() != "":
        p = Path(cli_config).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
        if not p.is_file():
            print(f"error: config file not found: {p}", file=sys.stderr)
            return None
        return str(p)

    env_val = os.environ.get(_ENV_CASMGR_CONFIG, "").strip()
    if env_val:
        p = Path(env_val).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
        if not p.is_file():
            print(
                f"error: {_ENV_CASMGR_CONFIG} points to missing file: {p}",
                file=sys.stderr,
            )
            return None
        return str(p)

    if _SYSTEM_DEFAULT_CONFIG.is_file():
        return str(_SYSTEM_DEFAULT_CONFIG.resolve())

    cwd_cfg = (Path.cwd() / _CWD_CONFIG_NAME).resolve()
    if cwd_cfg.is_file():
        return str(cwd_cfg)

    print(
        "error: no config found; pass --config, set "
        f"{_ENV_CASMGR_CONFIG}, install {_SYSTEM_DEFAULT_CONFIG}, "
        f"or run from a directory containing {_CWD_CONFIG_NAME}.",
        file=sys.stderr,
    )
    return None


def _find_venv_python_near_config(config_path: str) -> Optional[str]:
    """
    Locate a project virtualenv interpreter next to the config file.

    Walks from ``config.json``'s directory upward (parents), looking for
    ``.venv/bin/python`` or ``venv/bin/python`` (``Scripts/python.exe`` on
    Windows). Prefer this over ``sys.executable`` so ``start`` works even when
    the CLI was invoked with system Python.

    Returns:
        Path to the interpreter, or None if not found.
    """

    cfg = Path(config_path).resolve()
    base: Path = cfg.parent
    while True:
        for venv_name in (".venv", "venv"):
            if sys.platform == "win32":
                py = base / venv_name / "Scripts" / "python.exe"
            else:
                py = base / venv_name / "bin" / "python"
            try:
                if py.is_file() and os.access(py, os.X_OK):
                    # Do not use Path.resolve() here: it follows the symlink to the
                    # system interpreter, so the child would run *without* venv
                    # site-packages (argv[0] must stay under .venv). absolute() only
                    # normalizes to a full path.
                    return str(py.absolute())
            except OSError:
                continue
        if base == base.parent:
            break
        base = base.parent
    return None


def _project_root_dir(config_path: str) -> Path:
    """Directory containing the config file (project root for ``cwd``)."""

    return Path(config_path).resolve().parent


def _config_path_relative_to_root(config_path: str) -> str:
    """
    Return ``config_path`` relative to the project root (config file's parent).

    Daemon argv and CLI defaults use this form (e.g. ``config.json``) so paths
    do not embed the host filesystem prefix.
    """

    resolved = Path(config_path).resolve()
    root = resolved.parent
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        return str(resolved)


def _activate_project_root(config_path: str) -> str:
    """
    Set process ``cwd`` to the project root and return a project-relative config path.

    Args:
        config_path: Path to an existing config file (absolute or relative).

    Returns:
        Config path relative to the project root.

    Raises:
        OSError: If ``chdir`` to the project root fails.
    """

    resolved = Path(config_path).resolve()
    os.chdir(resolved.parent)
    return _config_path_relative_to_root(str(resolved))


def _python_executable_for_daemon(config_path: str) -> str:
    """
    Python binary used to spawn ``code_analysis.main --daemon``.

    Order:
    1. ``CODE_ANALYSIS_DAEMON_PYTHON`` if set and executable.
    2. ``.venv`` / ``venv`` found walking up from the config path.
    3. ``sys.executable`` (CLI interpreter).
    """

    override = os.environ.get(_ENV_DAEMON_PYTHON, "").strip()
    if override:
        p = Path(override).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p.absolute())
    found = _find_venv_python_near_config(config_path)
    if found is not None:
        return found
    return sys.executable


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


def _append_manager_log(config_path: str, level: str, message: str) -> None:
    """Append a casmgr diagnostic line to the daemon log when possible."""

    log_path = _daemon_log_file(config_path)
    if log_path is None:
        return
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts} | {level.upper():<7} | casmgr | {message}\n")
    except OSError:
        return


def _resolved_config_path_for_daemon_pid(pid: int, cfg_argv: str) -> Optional[str]:
    """
    Resolve the on-disk config path for a daemon given its ``--config`` argv.

    Relative paths are resolved using the process working directory (Linux:
    ``/proc/<pid>/cwd``). On non-Linux or if resolution fails, returns None.

    Args:
        pid: OS process id of the daemon.
        cfg_argv: Value after ``--config`` in the process argv.

    Returns:
        Absolute resolved config path, or None.
    """

    try:
        p = Path(cfg_argv)
        if p.is_absolute():
            return str(p.resolve())
        if sys.platform != "linux":
            return None
        cwd_link = Path(f"/proc/{pid}/cwd")
        if not cwd_link.exists():
            return None
        return str((cwd_link.resolve() / p).resolve())
    except Exception:
        return None


def _same_config_file(path_a: Optional[str], path_b: str) -> bool:
    """
    True when both paths refer to the same config file.

    String compare first; then inode compare (bind-mount / container ``/workspace``
    vs host path to the same file).
    """

    if path_a is None:
        return False
    if path_a == path_b:
        return True
    try:
        return os.path.samefile(path_a, path_b)
    except OSError:
        return False


def _wait_until_daemon_stable_or_dead(
    pid: int,
    *,
    stable_seconds: float = 1.25,
    max_wait_seconds: float = 20.0,
) -> bool:
    """
    Wait until the process has stayed alive for ``stable_seconds`` or exits.

    Catches immediate crashes (wrong interpreter, import errors) while allowing
    a short startup window; does not wait for HTTP listen (that can take longer).

    Returns:
        True if PID is still alive after ``stable_seconds`` (within max wait).
        False if the process disappears before stabilizing.
    """

    t0 = time.time()
    while time.time() - t0 < max_wait_seconds:
        if not _is_alive(pid):
            return False
        if time.time() - t0 >= stable_seconds:
            return True
        time.sleep(0.1)
    return _is_alive(pid)


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


def _is_zombie(pid: int) -> bool:
    """True if ``pid`` is a zombie (defunct). Excluded from daemon discovery."""

    if sys.platform != "linux":
        return False
    try:
        status_path = Path(f"/proc/{pid}/status")
        if not status_path.is_file():
            return False
        for line in status_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("State:"):
                parts = line.split()
                if len(parts) < 2:
                    return False
                # e.g. "State: Z (zombie)"
                return parts[1].upper().startswith("Z")
    except OSError:
        return False
    return False


def _is_effectively_dead(pid: int) -> bool:
    """True if PID is gone or only a zombie (no longer a real running process)."""

    if not _is_alive(pid):
        return True
    return _is_zombie(pid)


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
        if _is_effectively_dead(pid):
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

    # Zombies still appear in ``ps`` and answer ``kill(0)``; they are not daemons.
    living = _matching_daemon_argv_pids(config_path)
    return _root_daemon_pids_only(
        living,
        pidfile_pid=_read_pid(_default_pidfile_path(config_path)),
        known_worker_pids=_known_worker_pids(config_path),
    )


def _read_ppid(pid: int) -> Optional[int]:
    """Return parent PID from ``/proc`` (Linux only)."""

    if sys.platform != "linux":
        return None
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in status.splitlines():
        if line.startswith("PPid:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def _read_pgid(pid: int) -> Optional[int]:
    """Return process group id, or None when unavailable."""

    try:
        return os.getpgid(pid)
    except (OSError, ProcessLookupError):
        return None


def _worker_pid_files(config_path: str) -> list[Path]:
    """Known worker PID files under the configured log directory."""

    log_path = _daemon_log_file(config_path)
    if log_path is None:
        return []
    log_dir = log_path.parent
    return [
        log_dir / "indexing_worker.pid",
        log_dir / "vectorization_worker.pid",
        log_dir / "file_watcher_worker.pid",
        log_dir / "database_driver.pid",
    ]


def _known_worker_pids(config_path: str) -> set[int]:
    """Return live worker PIDs recorded in worker PID files."""

    out: set[int] = set()
    for pid_file in _worker_pid_files(config_path):
        pid = _read_pid(pid_file)
        if pid is not None and _is_alive(pid) and not _is_zombie(pid):
            out.add(pid)
    return out


def _matching_daemon_argv_pids(config_path: str) -> list[int]:
    """Find live PIDs whose argv looks like this config's daemon command."""

    cfg_resolved = str(Path(config_path).resolve())

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

        if _same_config_file(cfg_val, config_path) or _same_config_file(
            cfg_val, cfg_resolved
        ):
            pids.append(pid)
            continue

        resolved = _resolved_config_path_for_daemon_pid(pid, cfg_val)
        if _same_config_file(resolved, cfg_resolved):
            pids.append(pid)

    return [p for p in sorted(set(pids)) if not _is_zombie(p)]


def _root_daemon_pids_only(
    pids: list[int],
    *,
    pidfile_pid: Optional[int] = None,
    known_worker_pids: Optional[set[int]] = None,
) -> list[int]:
    """
    Keep only top-level PIDs when several processes share the same argv.

    Forked children inherit ``code_analysis.main --config … --daemon`` in
    ``/proc/pid/cmdline`` until exec; they must not be counted as separate
    daemons for status/start.
    """

    if not pids:
        return []
    if sys.platform != "linux":
        return sorted(pids)

    s = set(pids)
    known_workers = known_worker_pids or set()
    roots: list[int] = []
    for pid in sorted(s):
        if pid in known_workers:
            continue
        ppid = _read_ppid(pid)
        if ppid is not None and ppid in s:
            continue

        pgid = _read_pgid(pid)
        if pgid is not None and pid != pgid:
            if pgid in s:
                continue
            if (
                pidfile_pid is not None
                and pgid == pidfile_pid
                and not _is_alive(pidfile_pid)
            ):
                continue
            if len(s) > 1:
                continue

        roots.append(pid)
    return roots


def _find_stale_daemon_child_pids(config_path: str) -> list[int]:
    """Return daemon-argv PIDs that are not the actual root daemon."""

    candidates = _matching_daemon_argv_pids(config_path)
    pidfile_pid = _read_pid(_default_pidfile_path(config_path))
    roots = set(
        _root_daemon_pids_only(
            candidates,
            pidfile_pid=pidfile_pid,
            known_worker_pids=_known_worker_pids(config_path),
        )
    )
    return [pid for pid in candidates if pid not in roots]


def _daemon_log_file(config_path: str) -> Path | None:
    """
    Resolve daemon log file path from config so stderr can be redirected there.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Path to mcp_server.log, or None if config cannot be read.
    """
    try:
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except Exception:
        return None
    server = cfg.get("server")
    if not isinstance(server, dict):
        return None
    log_dir_str = server.get("log_dir", "./logs")
    log_dir = Path(log_dir_str)
    if not log_dir.is_absolute():
        log_dir = (Path(config_path).resolve().parent / log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "mcp_server.log"


def _spawn_daemon(config_path: str, pidfile: Path) -> int:
    """
    Spawn daemon server process.

    stderr is redirected to server log file (from config server.log_dir)
    so that crash tracebacks and errors are visible in logs.

    Passes a **project-relative** ``--config`` (e.g. ``config.json``) and sets
    ``cwd`` to the project root so ``ps``/``_find_daemon_pids`` and container
    mounts do not depend on the host path prefix.

    Args:
        config_path: Path to config JSON (relative to project root when possible).
        pidfile: Path to pidfile to write.

    Returns:
        PID of spawned process.
    """
    cfg_abs = str(Path(config_path).resolve())
    cfg_argv = _config_path_relative_to_root(cfg_abs)
    project_root = str(_project_root_dir(config_path))
    python = _python_executable_for_daemon(config_path)
    args = [python, "-m", "code_analysis.main", "--config", cfg_argv, "--daemon"]

    stderr_dest: _StderrDest = subprocess.DEVNULL
    log_file_path = _daemon_log_file(cfg_abs)
    if log_file_path is not None:
        try:
            stderr_dest = open(log_file_path, "a", encoding="utf-8")
        except OSError:
            stderr_dest = subprocess.DEVNULL

    child_env = os.environ.copy()
    child_env.setdefault("PYTHONUNBUFFERED", "1")

    try:
        proc = subprocess.Popen(
            args,
            cwd=project_root,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr_dest,
            start_new_session=True,
            close_fds=True,
        )
        pidfile.write_text(str(proc.pid), encoding="utf-8")
        return proc.pid
    finally:
        if stderr_dest is not subprocess.DEVNULL and hasattr(stderr_dest, "close"):
            stderr_dest.close()


def _cmd_status(config_path: str) -> int:
    """
    Print daemon status.

    Uses the same process discovery as ``stop`` (``_find_daemon_pids``), not only
    the pidfile. Otherwise ``status`` could report *stopped* while a daemon for
    this config is running (e.g. pidfile deleted, or started via ``main`` without
    going through ``start``).

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    pidfile = _default_pidfile_path(config_path)
    pf_pid = _read_pid(pidfile)
    daemons = _find_daemon_pids(config_path)
    stale_children = _find_stale_daemon_child_pids(config_path)

    if daemons:
        if len(daemons) == 1:
            d = daemons[0]
            if pf_pid == d:
                print(f"running pid={d}")
            elif pf_pid is None:
                print(f"running pid={d} (pidfile missing)")
            else:
                print(f"running pid={d} (pidfile pid={pf_pid} does not match)")
        else:
            print(f"running multiple pids={','.join(str(p) for p in daemons)}")
            _append_manager_log(
                config_path,
                "WARNING",
                "multiple root daemon processes discovered: "
                + ",".join(str(p) for p in daemons),
            )
        if stale_children:
            _append_manager_log(
                config_path,
                "WARNING",
                "stale daemon child/worker processes also present: "
                + ",".join(str(p) for p in stale_children),
            )
        return 0

    if stale_children:
        print(
            "stopped (stale daemon child processes: "
            + ",".join(str(p) for p in stale_children)
            + ")"
        )
        _append_manager_log(
            config_path,
            "WARNING",
            "daemon root is absent but stale child/worker processes remain: "
            + ",".join(str(p) for p in stale_children),
        )
        return 0

    if pf_pid is None:
        print("stopped")
        return 0
    if not _is_alive(pf_pid):
        print("stopped (stale pidfile)")
        _append_manager_log(
            config_path,
            "WARNING",
            f"stale pidfile removed: {pidfile} pid={pf_pid} is not alive",
        )
        try:
            pidfile.unlink(missing_ok=True)
        except OSError:
            pass
        return 0
    print(
        f"stopped (pidfile pid={pf_pid} alive but no daemon for this config; "
        "pidfile likely stale)"
    )
    _append_manager_log(
        config_path,
        "WARNING",
        f"pidfile pid={pf_pid} is alive but is not this config's daemon",
    )
    return 0


def _cmd_sessions(config_path: str) -> int:
    """
    Print all client sessions as an aligned table.

    Reads client sessions via SessionService using DatabaseClient.
    Always shows session_id (operator interface; ignores show_session_ids config).

    Columns: session_id | comment | created_at | last_active_at | locks

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """
    try:
        db = create_database_client_from_config_path(Path(config_path))
        rows = list_client_sessions(db)
        print(
            f"{'session_id':<36}  {'comment':<30}  {'created_at':<19}  {'last_active_at':<19}  locks"
        )
        print("-" * 120)
        for row in rows:
            session_id = str(row["session_id"])
            cnt = count_session_file_locks(db, session_id)
            created_at = row.get("created_at")
            created = _julianday_to_iso(
                float(created_at) if isinstance(created_at, (int, float)) else None
            )
            last_active = row.get("last_active_at")
            active = _julianday_to_iso(
                float(last_active) if isinstance(last_active, (int, float)) else None
            )
            comment = str(row.get("comment") or "")[:30]
            print(
                f"{session_id:<36}  {comment:<30}  {created:<19}  {active:<19}  {cnt}"
            )
        print(f"\n{len(rows)} session(s).")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_locks(config_path: str) -> int:
    """
    Print all locked files as an aligned table (session_id intentionally omitted).

    Reads all SessionFileLocks via SessionService using DatabaseClient.

    Columns: project_id | file_id | locked_at

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """
    try:
        db = create_database_client_from_config_path(Path(config_path))
        rows = list_locked_files(db)
        print(f"{'project_id':<36}  {'file_id':<36}  locked_at")
        print("-" * 95)
        for row in rows:
            locked_at = row.get("locked_at")
            locked = _julianday_to_iso(
                float(locked_at) if isinstance(locked_at, (int, float)) else None
            )
            print(f"{str(row['project_id']):<36}  {str(row['file_id']):<36}  {locked}")
        print(f"\n{len(rows)} lock(s).")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _julianday_to_iso(jd: Optional[float]) -> str:
    """
    Convert a SQLite julianday float to an ISO 8601 datetime string (UTC).

    Args:
        jd: Julian day number as float, or None.

    Returns:
        ISO datetime string 'YYYY-MM-DD HH:MM:SS', or '-' if jd is None.
    """
    if jd is None:
        return "-"
    try:
        unix_ts = (jd - 2440587.5) * 86400.0
        dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(jd)


def _cmd_stop(config_path: str) -> int:
    """
    Stop daemon process.

    Re-scans for matching PIDs each round so a single ``restart`` cannot leave a
    second daemon alive (race between SIGTERM and ``ps``).

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    grace = _read_shutdown_grace_seconds(config_path)
    pidfile = _default_pidfile_path(config_path)

    for _ in range(_STOP_MAX_ROUNDS):
        pid = _read_pid(pidfile)
        discovered = _find_daemon_pids(config_path)
        stale_children = _find_stale_daemon_child_pids(config_path)
        merged: list[int] = []
        if pid is not None:
            merged.append(pid)
        for p in discovered:
            if p not in merged:
                merged.append(p)
        for p in stale_children:
            if p not in merged:
                merged.append(p)

        alive = [p for p in merged if _is_alive(p) and not _is_zombie(p)]
        if not alive:
            break

        _append_manager_log(
            config_path,
            "WARNING",
            "stopping daemon process group(s); pids=" + ",".join(str(p) for p in alive),
        )
        for p in alive:
            _kill_process_group(p, timeout_s=grace)
        time.sleep(_STOP_ROUND_DELAY_S)

    try:
        pidfile.unlink(missing_ok=True)
    except Exception:
        # Best effort cleanup; stale pidfile is handled by status/start.
        pass
    return 0


def _wait_until_no_daemons(config_path: str, *, timeout_s: float) -> bool:
    """Poll until ``_find_daemon_pids`` is empty or ``timeout_s`` elapses."""

    deadline = time.time() + max(timeout_s, 0.1)
    while time.time() < deadline:
        if not _find_daemon_pids(config_path):
            return True
        time.sleep(_STOP_ROUND_DELAY_S)
    return not bool(_find_daemon_pids(config_path))


def _cmd_start(config_path: str) -> int:
    """
    Start daemon process (if not already running).

    Uses the same discovery as ``status``/``stop`` (``_find_daemon_pids``), not
    only the pidfile, so we do not start a second server when a daemon is already
    running but the pidfile is missing or stale.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    pidfile = _default_pidfile_path(config_path)
    daemons = _find_daemon_pids(config_path)
    stale_children = _find_stale_daemon_child_pids(config_path)

    if len(daemons) > 1:
        print(
            f"error: multiple daemons for this config (pids={','.join(str(p) for p in daemons)}); "
            "run stop first",
            file=sys.stderr,
        )
        _append_manager_log(
            config_path,
            "ERROR",
            "refusing start because multiple root daemons are present: "
            + ",".join(str(p) for p in daemons),
        )
        return 1

    if len(daemons) == 1:
        if stale_children:
            _append_manager_log(
                config_path,
                "WARNING",
                "daemon is running but stale child/worker processes also remain: "
                + ",".join(str(p) for p in stale_children),
            )
        try:
            pidfile.write_text(str(daemons[0]), encoding="utf-8")
        except OSError as e:
            print(f"error: cannot write pidfile: {e}", file=sys.stderr)
            return 1
        print(f"already running pid={daemons[0]}")
        return 0

    if stale_children:
        _append_manager_log(
            config_path,
            "WARNING",
            "cleaning stale daemon child/worker processes before start: "
            + ",".join(str(p) for p in stale_children),
        )
        grace = _read_shutdown_grace_seconds(config_path)
        for p in stale_children:
            if _is_alive(p) and not _is_zombie(p):
                _kill_process_group(p, timeout_s=grace)
        time.sleep(_RESTART_SETTLE_S)

    try:
        pidfile.unlink(missing_ok=True)
    except Exception:
        pass

    py_exe = _python_executable_for_daemon(config_path)
    root = _project_root_dir(config_path)
    print(f"daemon: python={py_exe} cwd={root}", file=sys.stderr)

    new_pid = _spawn_daemon(config_path, pidfile)
    print(f"started pid={new_pid}")
    if not _wait_until_daemon_stable_or_dead(new_pid):
        log_hint = _daemon_log_file(str(Path(config_path).resolve()))
        where = (
            str(log_hint)
            if log_hint is not None
            else "server log (see config server.log_dir)"
        )
        print(
            f"error: daemon pid={new_pid} exited during startup; check {where}",
            file=sys.stderr,
        )
        try:
            pidfile.unlink(missing_ok=True)
        except OSError:
            pass
        return 1
    return 0


def _cmd_restart(config_path: str) -> int:
    """
    Restart daemon process.

    Waits until discovery reports no daemons for this config before ``start``,
    so a new instance is not stacked on a still-shutting-down one.

    Args:
        config_path: Path to server config JSON.

    Returns:
        Exit code.
    """

    grace = _read_shutdown_grace_seconds(config_path)
    _cmd_stop(config_path)
    drain_timeout = max(45.0, grace * 4.0 + 5.0)
    if not _wait_until_no_daemons(config_path, timeout_s=drain_timeout):
        daemons = _find_daemon_pids(config_path)
        print(
            "error: daemon process(es) still present after stop; "
            f"pids={','.join(str(p) for p in daemons)} — run `casmgr --config … stop` "
            "manually, then `start`.",
            file=sys.stderr,
        )
        return 1
    time.sleep(_RESTART_SETTLE_S)
    return _cmd_start(config_path)


def server(argv: Optional[list[str]] = None) -> int:
    """
    Console entrypoint for the daemon manager (installed script: ``casmgr``).

    Args:
        argv: Optional argv override.

    Returns:
        Exit code.
    """

    parser = argparse.ArgumentParser(prog="casmgr")
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help=(
            "Path to config.json (optional). If omitted: "
            f"{_ENV_CASMGR_CONFIG}, then {_SYSTEM_DEFAULT_CONFIG}, "
            f"then ./{_CWD_CONFIG_NAME} in the current directory."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("restart")
    sub.add_parser("status")
    sub.add_parser("sessions", help="List all client sessions.")
    sub.add_parser("locks", help="List all file locks across all sessions.")
    ns = parser.parse_args(argv)

    config_path_abs = _resolve_config_path(ns.config)
    if config_path_abs is None:
        return 2
    try:
        config_path = _activate_project_root(config_path_abs)
    except OSError as exc:
        print(
            f"error: cannot change to project root for config: {exc}",
            file=sys.stderr,
        )
        return 2

    if ns.cmd == "start":
        return _cmd_start(config_path)
    if ns.cmd == "stop":
        return _cmd_stop(config_path)
    if ns.cmd == "restart":
        return _cmd_restart(config_path)
    if ns.cmd == "status":
        return _cmd_status(config_path)
    if ns.cmd == "sessions":
        return _cmd_sessions(config_path)
    if ns.cmd == "locks":
        return _cmd_locks(config_path)

    raise RuntimeError(f"Unknown command: {ns.cmd}")


if __name__ == "__main__":
    raise SystemExit(server())
