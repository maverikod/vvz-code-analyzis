"""
Runtime configuration validity state (re-validated on each config load, subject to
the per-path mtime/size cache below).

When invalid, MCP commands are blocked except ``help`` and ``health``.

Bug 8e6acb34 (component B): every ``load_raw_config``/``revalidate_config_at_path``
call used to re-parse ``config.json`` (commentjson + lark) AND re-run the full
semantic validator -- including 8 ``load_pem_private_key`` RSA parses inside
``CertificateValidator.validate_certificate_key_match`` -- unconditionally, on
EVERY command call across ~20 call sites (measured ~0.5s/call, 58% of a read
command's CPU-bound body). This was the ``load_raw_config`` cache explicitly
deferred by ``server_instance.py`` (bug 9f5d860e follow-up note) -- implemented
here instead of a second, narrower memoization: cache the validated result keyed
on the resolved config path plus its ``(mtime_ns, size)``, so an edited config is
still picked up on the next call, but an unchanged file is served from the
in-process cache without re-parsing or re-validating. A failed validation is
cached exactly as it occurred (its own ``valid=False`` outcome, not coerced to
success) so a broken config stays reported broken until the file changes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from code_analysis.core.config_errors import (
    format_config_json_error_report,
    format_validation_error_report,
    format_validation_result_line,
)
from code_analysis.core.config_json import ConfigJSONDecodeError, load_config_json
from code_analysis.core.config_validator import CodeAnalysisConfigValidator

logger = logging.getLogger(__name__)

ALLOWED_COMMANDS_WHEN_CONFIG_INVALID: FrozenSet[str] = frozenset({"help", "health"})


@dataclass
class ConfigRuntimeState:
    """Thread-safe snapshot of the last config validation outcome."""

    valid: bool = True
    config_path: Optional[Path] = None
    error_lines: List[str] = field(default_factory=list)
    warning_lines: List[str] = field(default_factory=list)
    last_config_data: Optional[Dict[str, Any]] = None

    def summary(self) -> Dict[str, Any]:
        """Return summary."""
        return {
            "valid": self.valid,
            "config_path": str(self.config_path) if self.config_path else None,
            "errors": list(self.error_lines),
            "warnings": list(self.warning_lines),
        }


_lock = threading.Lock()
_state = ConfigRuntimeState()


def get_config_runtime_state() -> ConfigRuntimeState:
    """Return get config runtime state."""
    with _lock:
        return ConfigRuntimeState(
            valid=_state.valid,
            config_path=_state.config_path,
            error_lines=list(_state.error_lines),
            warning_lines=list(_state.warning_lines),
            last_config_data=_state.last_config_data,
        )


def is_config_valid() -> bool:
    """Return is config valid."""
    with _lock:
        return _state.valid


def config_blocks_command(command_name: Optional[str]) -> bool:
    """Return config blocks command."""
    if is_config_valid():
        return False
    if not command_name:
        return True
    return command_name.strip().lower() not in ALLOWED_COMMANDS_WHEN_CONFIG_INVALID


def config_invalid_command_message() -> str:
    """Return config invalid command message."""
    st = get_config_runtime_state()
    lines = [
        "Server is in configuration error state; only help and health are available."
    ]
    if st.error_lines:
        lines.append("Configuration errors:")
        for line in st.error_lines:
            if line.startswith("Fix the issues") or line.startswith("Validate after"):
                continue
            lines.append(f"  {line}" if line.startswith("  ") else f"  {line}")
    if st.config_path:
        lines.append(f"Config file: {st.config_path}")
    lines.append(
        "Fix config.json, then run: casmgr-config-validate --file "
        + (str(st.config_path) if st.config_path else "<config.json>")
    )
    return "\n".join(lines)


def _set_state(
    *,
    valid: bool,
    config_path: Optional[Path],
    error_lines: List[str],
    warning_lines: List[str],
    config_data: Optional[Dict[str, Any]],
) -> None:
    """Return set state."""
    global _state
    with _lock:
        _state = ConfigRuntimeState(
            valid=valid,
            config_path=config_path,
            error_lines=error_lines,
            warning_lines=warning_lines,
            last_config_data=config_data,
        )


def mark_config_invalid_from_exception(
    exc: Exception,
    *,
    config_path: Optional[Path] = None,
) -> None:
    """Return mark config invalid from exception."""
    if isinstance(exc, ConfigJSONDecodeError):
        report = str(exc) or format_config_json_error_report(
            exc,
            config_path=config_path or exc.source_path,
            source_text=exc.source_text,
        )
        _set_state(
            valid=False,
            config_path=config_path or exc.source_path,
            error_lines=report.splitlines(),
            warning_lines=[],
            config_data=None,
        )
        logger.error("Configuration JSON invalid:\n%s", report)
        return

    _set_state(
        valid=False,
        config_path=config_path,
        error_lines=[str(exc)],
        warning_lines=[],
        config_data=None,
    )
    logger.error("Configuration invalid: %s", exc)


@dataclass(frozen=True)
class _CachedConfigValidation:
    """One process-cached ``revalidate_config_at_path`` outcome for one config path."""

    stat_key: Tuple[int, int]  # (mtime_ns, size) at the time this entry was built
    config_data: Dict[str, Any]
    valid: bool
    error_lines: List[str]
    warning_lines: List[str]


# Per-path validation cache: guarded by its own lock (separate from ``_lock`` above,
# which guards the *externally visible* runtime-state snapshot) so a cache hit never
# blocks on, or is blocked by, an unrelated ``get_config_runtime_state()`` reader.
# Safe under concurrent offload-worker threads: the lock is held only around the
# dict read/write, never across the (possibly slow) parse+validate call, so a
# concurrent miss on the same path may redundantly validate at most once per actual
# change -- never a correctness issue, only a rare, bounded duplicate of work that
# would have happened unconditionally before this cache existed.
_validation_cache_lock = threading.Lock()
_validation_cache: Dict[str, _CachedConfigValidation] = {}
_config_validation_load_count = 0
_config_validation_cache_hit_count = 0


def _stat_key(path: Path) -> Optional[Tuple[int, int]]:
    """Return ``(mtime_ns, size)`` for ``path``, or ``None`` if it cannot be stat'd."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def get_config_validation_cache_diagnostics() -> Dict[str, int]:
    """
    Return counters for the per-path config validation cache (bug 8e6acb34 gate).

    ``load_count`` increments once per real parse+validate (cache miss or first
    call for a path); ``cache_hit_count`` increments once per call served from the
    in-process cache without touching disk or the validator.
    """
    with _validation_cache_lock:
        return {
            "load_count": _config_validation_load_count,
            "cache_hit_count": _config_validation_cache_hit_count,
        }


def reset_config_validation_cache() -> None:
    """Clear the per-path config validation cache (test / hot-reload hook)."""
    global _config_validation_load_count, _config_validation_cache_hit_count
    with _validation_cache_lock:
        _validation_cache.clear()
        _config_validation_load_count = 0
        _config_validation_cache_hit_count = 0


def revalidate_config_at_path(config_path: Path) -> tuple[Dict[str, Any], bool]:
    """
    Parse and semantically validate ``config.json``, cached per process.

    Updates global runtime state. Returns ``(config_data, is_valid)``.
    Raises ``ConfigJSONDecodeError`` on syntax failure (state marked invalid).

    Cached on ``(resolved_path, mtime_ns, size)``: an unchanged file is served
    from the in-process cache (no re-parse, no re-validate, no repeated
    ``load_pem_private_key`` calls); editing the file (mtime/size change) always
    triggers a fresh parse+validate on the next call. A cache hit still refreshes
    the externally visible runtime state (:func:`get_config_runtime_state`) from
    the cached outcome, so callers observe identical behavior to an uncached call
    -- including a cached FAILED validation, which is served back as the same
    failure, never coerced into success.
    """
    global _config_validation_load_count, _config_validation_cache_hit_count

    path = Path(config_path).resolve()
    path_key = str(path)
    stat_key = _stat_key(path)

    if stat_key is not None:
        with _validation_cache_lock:
            cached = _validation_cache.get(path_key)
            if cached is not None and cached.stat_key == stat_key:
                _config_validation_cache_hit_count += 1
                hit = cached
            else:
                hit = None
        if hit is not None:
            _set_state(
                valid=hit.valid,
                config_path=path,
                error_lines=list(hit.error_lines),
                warning_lines=list(hit.warning_lines),
                config_data=hit.config_data,
            )
            return hit.config_data, hit.valid

    try:
        config_data = load_config_json(path)
    except ConfigJSONDecodeError as exc:
        mark_config_invalid_from_exception(exc, config_path=path)
        raise

    validator = CodeAnalysisConfigValidator(str(path))
    validator.config_data = config_data
    results = validator.validate_config(config_data)
    summary = validator.get_validation_summary()

    warning_lines = [
        format_validation_result_line(r) for r in results if r.level == "warning"
    ]

    if summary["is_valid"]:
        valid = True
        error_lines: List[str] = []
    else:
        valid = False
        error_lines = format_validation_error_report(results, config_path=path).splitlines()

    _set_state(
        valid=valid,
        config_path=path,
        error_lines=error_lines,
        warning_lines=warning_lines,
        config_data=config_data,
    )

    if stat_key is not None:
        with _validation_cache_lock:
            _validation_cache[path_key] = _CachedConfigValidation(
                stat_key=stat_key,
                config_data=config_data,
                valid=valid,
                error_lines=list(error_lines),
                warning_lines=list(warning_lines),
            )
            _config_validation_load_count += 1

    if valid:
        if warning_lines:
            logger.warning(
                "Configuration valid with %s warning(s):\n%s",
                len(warning_lines),
                "\n".join(f"  - {w}" for w in warning_lines),
            )
        return config_data, True

    logger.error(
        "Configuration validation failed:\n%s", "\n".join(error_lines)
    )
    return config_data, False
