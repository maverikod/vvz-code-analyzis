"""
Boot-parity worker start-argument resolvers (bug 827e2b05).

Manual ``start_worker`` (``code_analysis/commands/start_worker_mcp_command.py``)
used to build its own ad-hoc kwargs for ``WorkerManager.start_*_worker``,
diverging from what the server computes at boot (``code_analysis/main_workers.py``)
for all three worker types:

- vectorization: manual defaulted ``worker_log_path`` under the passed project
  root instead of ``storage.log_dir``, and built ``svo_config`` by passing the
  ENTIRE ``code_analysis`` config section unfiltered into ``ServerConfig(**...)``.
  ``ServerConfig`` has ``model_config = {"extra": "forbid"}`` and a real config
  always has a ``database`` key (plus e.g. ``storage``) that is not a
  ``ServerConfig`` field, so this deterministically raised ``ValidationError``,
  silently swallowed into ``svo_config = None`` -- the worker could chunk but
  never embed. It also ignored ``worker.batch_size`` / ``worker.poll_interval``
  / ``vector_dim`` and the ``worker.enabled`` kill-switch.
- indexing: manual never read ``code_analysis.indexing_worker`` at all --
  bypassing ``indexing_worker.enabled=false`` and using the wrong default
  ``batch_size`` (10 instead of boot's 5).
- file_watcher: same log-path divergence, plus it always forced a hardcoded
  ignore-pattern set instead of the config-driven one boot resolves through
  ``ServerConfig``.

This module is the single source of truth both call sites use: pure resolver
functions that port the boot logic verbatim (config filtering against
``ServerConfig.model_fields``, ``apply_resolved_batch_output_dir``, chunker/
config validation, enabled kill-switches, config-driven batch/poll/vector_dim/
log paths, absolute ``version_dir``, ``ignore_patterns``) and return a
structured :class:`WorkerStartPlan` -- never a silent ``None`` on
misconfiguration. ``main_workers.py`` startup_* functions and
``StartWorkerMCPCommand.execute`` both call these; explicit caller
``overrides`` (only keys the caller actually passed) win over config-derived
values.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from pydantic import ValidationError

from .config import ServerConfig
from .constants import DEFAULT_BATCH_SIZE, DEFAULT_POLL_INTERVAL
from .storage_paths import (
    apply_resolved_batch_output_dir,
    load_raw_config,
    resolve_storage_paths,
)

_DEFAULT_INDEXING_POLL_INTERVAL = 30
_DEFAULT_INDEXING_BATCH_SIZE = 5


@dataclass(frozen=True)
class WorkerStartPlan:
    """
    Result of resolving one worker type's start kwargs.

    Attributes:
        ok: True when ``kwargs`` is ready to pass to the matching
            ``WorkerManager.start_*_worker`` call.
        skip_reason: Human-readable reason the worker should NOT be started
            (disabled in config, missing/invalid config, ...). Always set
            when ``ok`` is False, always ``None`` when ``ok`` is True.
        kwargs: Resolved keyword arguments for the manager call. Always set
            when ``ok`` is True, always ``None`` when ``ok`` is False.
    """

    ok: bool
    skip_reason: Optional[str]
    kwargs: Optional[Dict[str, Any]]


def _skip(reason: str) -> WorkerStartPlan:
    """Build a not-ok :class:`WorkerStartPlan` carrying a skip reason."""
    return WorkerStartPlan(ok=False, skip_reason=reason, kwargs=None)


def _ready(kwargs: Dict[str, Any]) -> WorkerStartPlan:
    """Build an ok :class:`WorkerStartPlan` carrying resolved kwargs."""
    return WorkerStartPlan(ok=True, skip_reason=None, kwargs=kwargs)


def _resolve_abs_path(config_dir: Path, value: str) -> Path:
    """Resolve a path string (absolute or relative to ``config_dir``)."""
    p = Path(value).expanduser()
    if not p.is_absolute():
        p = (config_dir / p).resolve()
    return p.resolve()


def _build_server_config(
    code_analysis_config: Mapping[str, Any],
    config_path: Path,
    *,
    apply_batch_output_dir: bool,
) -> "ServerConfig | str":
    """
    Filter ``code_analysis_config`` to ``ServerConfig`` fields and validate.

    Mirrors ``main_workers.py`` boot logic: only keys that are actual
    ``ServerConfig`` fields are passed through (``ServerConfig`` rejects
    unknown keys via ``extra="forbid"``; a real config always carries
    non-field sections like ``database`` and ``storage``).

    Args:
        code_analysis_config: Raw ``config_data["code_analysis"]`` mapping.
        config_path: Path to the server config file (for relative resolution).
        apply_batch_output_dir: Whether to resolve ``batch_output_dir`` before
            validation (vectorization boot does this; file_watcher boot does
            not need it).

    Returns:
        A validated ``ServerConfig`` on success, or an error message string
        describing why validation failed.
    """
    allowed = set(ServerConfig.model_fields.keys())
    filtered = {k: v for k, v in code_analysis_config.items() if k in allowed}
    if apply_batch_output_dir:
        filtered = apply_resolved_batch_output_dir(filtered, config_path)
    try:
        return ServerConfig(**filtered)
    except ValidationError as e:
        return f"invalid code_analysis config: {e}"


def resolve_vectorization_worker_kwargs(
    app_config: Mapping[str, Any],
    config_path: Path,
    *,
    overrides: Optional[Mapping[str, Any]] = None,
) -> WorkerStartPlan:
    """
    Resolve kwargs for ``WorkerManager.start_vectorization_worker``.

    Ports ``main_workers.startup_vectorization_worker`` verbatim (model_fields
    filtering, ``apply_resolved_batch_output_dir``, chunker validation, the
    ``worker.enabled`` kill-switch, config-driven batch_size/poll_interval/
    vector_dim/log path) as a pure function -- no filesystem/DB side effects
    beyond reading config files.

    Args:
        app_config: Full raw app config dict (as loaded from config.json).
        config_path: Path to the server config file.
        overrides: Explicitly caller-supplied values that win over config
            derived ones. Recognized keys: ``vector_dim``, ``batch_size``,
            ``poll_interval``, ``worker_log_path``.

    Returns:
        WorkerStartPlan. Not-ok when there is no code_analysis config, the
        config fails ``ServerConfig`` validation, no chunker is configured,
        or the vectorization worker is disabled in config -- never a silent
        ``None`` svo_config.
    """
    code_analysis_config = (app_config or {}).get("code_analysis") or {}
    if not code_analysis_config:
        return _skip("no code_analysis config found")

    config_path = Path(config_path)
    built = _build_server_config(
        code_analysis_config, config_path, apply_batch_output_dir=True
    )
    if isinstance(built, str):
        return _skip(built)
    server_config = built

    if not server_config.chunker:
        return _skip("no chunker config found")

    worker_config = server_config.worker
    if (
        worker_config
        and isinstance(worker_config, dict)
        and not worker_config.get("enabled", True)
    ):
        return _skip("vectorization worker disabled in config")

    config_data = load_raw_config(config_path)
    storage = resolve_storage_paths(config_data=config_data, config_path=config_path)
    db_path = storage.db_path
    faiss_dir = storage.faiss_dir

    svo_config = apply_resolved_batch_output_dir(
        (
            server_config.model_dump()
            if hasattr(server_config, "model_dump")
            else server_config.dict()
        ),
        config_path,
    )

    vector_dim = server_config.vector_dim or 384
    batch_size = DEFAULT_BATCH_SIZE
    poll_interval = DEFAULT_POLL_INTERVAL
    worker_log_path: Optional[str] = None
    if worker_config and isinstance(worker_config, dict):
        batch_size = worker_config.get("batch_size", DEFAULT_BATCH_SIZE)
        poll_interval = worker_config.get("poll_interval", DEFAULT_POLL_INTERVAL)
        worker_log_path = worker_config.get("log_path")

    if worker_log_path:
        worker_log_path = str(Path(worker_log_path).parent / "vectorization_worker.log")
    else:
        worker_log_path = str(storage.log_dir / "vectorization_worker.log")

    if overrides:
        if overrides.get("vector_dim") is not None:
            vector_dim = overrides["vector_dim"]
        if overrides.get("batch_size") is not None:
            batch_size = overrides["batch_size"]
        if overrides.get("poll_interval") is not None:
            poll_interval = overrides["poll_interval"]
        if overrides.get("worker_log_path") is not None:
            worker_log_path = str(overrides["worker_log_path"])

    kwargs = {
        "db_path": str(db_path),
        "faiss_dir": str(faiss_dir),
        "config_path": str(config_path),
        "vector_dim": vector_dim,
        "svo_config": svo_config,
        "batch_size": batch_size,
        "poll_interval": poll_interval,
        "worker_log_path": worker_log_path,
        "worker_logs_dir": str(Path(worker_log_path).resolve().parent),
    }
    return _ready(kwargs)


def resolve_file_watcher_worker_kwargs(
    app_config: Mapping[str, Any],
    config_path: Path,
    *,
    overrides: Optional[Mapping[str, Any]] = None,
) -> WorkerStartPlan:
    """
    Resolve kwargs for ``WorkerManager.start_file_watcher_worker``.

    Ports ``main_workers.startup_file_watcher_worker`` verbatim (model_fields
    filtering, the ``file_watcher.enabled`` kill-switch, config-driven
    scan_interval/ignore_patterns/version_dir/log path) as a pure function.
    ``watch_dirs`` is NOT defaulted here -- boot discovers watch_dirs from
    config (``parse_worker_watch_dirs_raw``); a caller that wants the
    project-root-derived single-directory default used by manual
    project-scoped starts must pass it via ``overrides["watch_dirs"]``.

    Args:
        app_config: Full raw app config dict (as loaded from config.json).
        config_path: Path to the server config file.
        overrides: Explicitly caller-supplied values that win over config
            derived ones. Recognized keys: ``scan_interval``,
            ``worker_log_path``, ``watch_dirs`` (list of ``{"path", "id"}``
            dicts, already in manager-call shape).

    Returns:
        WorkerStartPlan. Not-ok when there is no code_analysis config, the
        config fails ``ServerConfig`` validation, no file_watcher config is
        present, or the file watcher is disabled in config.
    """
    code_analysis_config = (app_config or {}).get("code_analysis") or {}
    if not code_analysis_config:
        return _skip("no code_analysis config found")

    config_path = Path(config_path)
    built = _build_server_config(
        code_analysis_config, config_path, apply_batch_output_dir=False
    )
    if isinstance(built, str):
        return _skip(built)
    server_config = built

    file_watcher_config = server_config.file_watcher
    if not file_watcher_config or not isinstance(file_watcher_config, dict):
        return _skip("no file_watcher config found")
    if not file_watcher_config.get("enabled", True):
        return _skip("file watcher worker disabled in config")

    from ..main_workers_file_watcher import (
        build_file_watcher_watch_dir_entries,
        parse_worker_watch_dirs_raw,
    )

    config_dir = config_path.resolve().parent
    config_data = load_raw_config(config_path)
    storage = resolve_storage_paths(config_data=config_data, config_path=config_path)
    db_path = storage.db_path

    watch_dirs_config = build_file_watcher_watch_dir_entries(
        parse_worker_watch_dirs_raw(code_analysis_config)
    )

    scan_interval = file_watcher_config.get("scan_interval", 60)
    version_dir_raw = file_watcher_config.get("version_dir", "data/versions")
    version_dir = str(_resolve_abs_path(config_dir, str(version_dir_raw)))
    worker_log_path = file_watcher_config.get("log_path")
    ignore_patterns = file_watcher_config.get("ignore_patterns", [])
    locks_dir = storage.locks_dir

    if not worker_log_path:
        worker_log_path = str(storage.log_dir / "file_watcher.log")

    if overrides:
        if overrides.get("scan_interval") is not None:
            scan_interval = overrides["scan_interval"]
        if overrides.get("worker_log_path") is not None:
            worker_log_path = str(overrides["worker_log_path"])
        if overrides.get("watch_dirs") is not None:
            watch_dirs_config = overrides["watch_dirs"]

    kwargs = {
        "db_path": str(db_path),
        "watch_dirs": watch_dirs_config,
        "locks_dir": str(locks_dir),
        "config_path": str(config_path),
        "scan_interval": scan_interval,
        "version_dir": version_dir,
        "worker_log_path": worker_log_path,
        "worker_logs_dir": str(Path(worker_log_path).resolve().parent),
        "ignore_patterns": ignore_patterns,
    }
    return _ready(kwargs)


def resolve_indexing_worker_kwargs(
    app_config: Mapping[str, Any],
    config_path: Path,
    *,
    overrides: Optional[Mapping[str, Any]] = None,
) -> WorkerStartPlan:
    """
    Resolve kwargs for ``WorkerManager.start_indexing_worker``.

    Ports ``main_workers.startup_indexing_worker`` verbatim (reads
    ``code_analysis.indexing_worker``, honors its ``enabled`` kill-switch and
    config-driven poll_interval/batch_size/log_path, plus
    ``worker.log_all_operations_timing``) as a pure function. Manual
    ``start_worker`` previously never read this section at all.

    Args:
        app_config: Full raw app config dict (as loaded from config.json).
        config_path: Path to the server config file.
        overrides: Explicitly caller-supplied values that win over config
            derived ones. Recognized keys: ``poll_interval``, ``batch_size``,
            ``worker_log_path``.

    Returns:
        WorkerStartPlan. Not-ok only when ``indexing_worker.enabled`` is
        explicitly ``false`` in config.
    """
    code_analysis_config = (app_config or {}).get("code_analysis") or {}
    indexing_cfg = code_analysis_config.get("indexing_worker") or {}
    if isinstance(indexing_cfg, dict) and not indexing_cfg.get("enabled", True):
        return _skip("indexing worker disabled in config")

    config_path = Path(config_path)
    config_data = load_raw_config(config_path)
    storage = resolve_storage_paths(config_data=config_data, config_path=config_path)
    db_path = storage.db_path

    poll_interval: Any = _DEFAULT_INDEXING_POLL_INTERVAL
    batch_size: Any = _DEFAULT_INDEXING_BATCH_SIZE
    worker_log_path = str(storage.log_dir / "indexing_worker.log")
    log_timing = False
    worker_cfg = code_analysis_config.get("worker") or {}
    if isinstance(worker_cfg, dict):
        log_timing = bool(worker_cfg.get("log_all_operations_timing", False))
    if isinstance(indexing_cfg, dict):
        poll_interval = indexing_cfg.get("poll_interval", _DEFAULT_INDEXING_POLL_INTERVAL)
        batch_size = indexing_cfg.get("batch_size", _DEFAULT_INDEXING_BATCH_SIZE)
        if indexing_cfg.get("log_path"):
            worker_log_path = indexing_cfg["log_path"]

    if overrides:
        if overrides.get("poll_interval") is not None:
            poll_interval = overrides["poll_interval"]
        if overrides.get("batch_size") is not None:
            batch_size = overrides["batch_size"]
        if overrides.get("worker_log_path") is not None:
            worker_log_path = str(overrides["worker_log_path"])

    kwargs = {
        "db_path": str(db_path),
        "config_path": str(config_path),
        "poll_interval": int(poll_interval),
        "batch_size": int(batch_size),
        "worker_log_path": worker_log_path,
        "worker_logs_dir": str(Path(worker_log_path).resolve().parent),
        "log_timing": log_timing,
    }
    return _ready(kwargs)
