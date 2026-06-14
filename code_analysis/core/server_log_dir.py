"""
Resolve server log directory and append early startup diagnostics.

Used before mcp-proxy-adapter ``setup_logging()`` (which defaults to ``./logs``)
and for production troubleshooting when the listener never becomes reachable.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_STARTUP_LOG_NAME = "server_startup.log"


def discover_config_path_from_argv(argv: Optional[list[str]] = None) -> Optional[Path]:
    """Return ``--config`` path from argv without importing the adapter."""
    args = argv if argv is not None else sys.argv
    for index, arg in enumerate(args):
        if arg == "--config" and index + 1 < len(args):
            return _normalize_config_path(args[index + 1])
        if arg.startswith("--config="):
            return _normalize_config_path(arg.split("=", 1)[1])
    return None


def discover_config_path_from_env() -> Optional[Path]:
    """Resolve config path from ``CASMGR_CONFIG`` when the file exists."""
    raw = (os.environ.get("CASMGR_CONFIG") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return path if path.is_file() else None


def _normalize_config_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return path


def server_log_dir_from_config_data(
    config_data: dict[str, Any],
    config_path: Path,
) -> Path:
    """Resolve ``server.log_dir`` relative to the config file directory."""
    server = config_data.get("server")
    if not isinstance(server, dict):
        server = {}
    log_dir_str = server.get("log_dir") or "./logs"
    if not isinstance(log_dir_str, str) or not log_dir_str.strip():
        log_dir_str = "./logs"
    log_dir = Path(log_dir_str).expanduser()
    if not log_dir.is_absolute():
        log_dir = (config_path.resolve().parent / log_dir).resolve()
    return log_dir


def resolve_server_log_dir(
    config_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    Resolve the directory for server and adapter log files.

    Priority:
    1. ``CASMGR_LOG`` / ``MCP_ADAPTER_LOG_DIR``
    2. ``server.log_dir`` from config (``--config`` argv, else ``CASMGR_CONFIG``)
    """
    explicit = (
        os.environ.get("CASMGR_LOG") or os.environ.get("MCP_ADAPTER_LOG_DIR") or ""
    ).strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    candidates: list[Path] = []
    if config_path is not None:
        candidates.append(config_path)
    argv_path = discover_config_path_from_argv()
    if argv_path is not None:
        candidates.append(argv_path)
    env_path = discover_config_path_from_env()
    if env_path is not None:
        candidates.append(env_path)

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        try:
            from code_analysis.core.config_json import load_config_json

            data = load_config_json(resolved)
            return server_log_dir_from_config_data(data, resolved)
        except Exception:
            continue
    return None


def append_server_startup_log(log_dir: Path, message: str) -> None:
    """Append one line to ``server_startup.log``; never raises."""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / _STARTUP_LOG_NAME
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"{ts} UTC | {message}\n")
    except OSError:
        pass


def log_path_diagnostics(log_dir: Path, label: str, paths: dict[str, str]) -> None:
    """Log existence of configured filesystem paths (certs, storage, etc.)."""
    for name, raw in paths.items():
        if not raw:
            append_server_startup_log(log_dir, f"{label}: {name}=<empty>")
            continue
        path = Path(raw).expanduser()
        if path.is_file():
            append_server_startup_log(log_dir, f"{label}: {name}={path} exists=file")
        elif path.is_dir():
            append_server_startup_log(log_dir, f"{label}: {name}={path} exists=dir")
        else:
            append_server_startup_log(log_dir, f"{label}: {name}={path} exists=no")
