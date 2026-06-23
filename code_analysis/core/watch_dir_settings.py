"""
Per watch-directory ``settings.json`` (deleted flag + ignore_patterns).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from code_analysis.core.fs_permissions import is_readable_file, is_writable_dir

logger = logging.getLogger(__name__)

WATCH_DIR_SETTINGS_FILENAME = "settings.json"

DEFAULT_WATCH_DIR_IGNORE_PATTERNS: list[str] = [
    "**/.venv/**",
    "**/venv/**",
    "**/ENV/**",
    "**/env/**",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/.mypy_cache/**",
    "**/.eggs/**",
    "**/eggs/**",
    "**/old_code/**",
    "**/data/**",
    "**/*.egg-info/**",
    "**/*.egg",
    "**/develop-eggs/**",
    "**/dist/**",
    "**/build/**",
    "**/wheels/**",
    "**/.tox/**",
    "**/.cache/**",
    "**/htmlcov/**",
    "**/.coverage",
    "**/node_modules/**",
    "**/test_data/**",
]


@dataclass(frozen=True, slots=True)
class WatchDirSettings:
    """Settings stored in each watch directory root."""

    deleted: bool
    ignore_patterns: tuple[str, ...]


def _settings_path(watch_dir: Path) -> Path:
    return watch_dir / WATCH_DIR_SETTINGS_FILENAME


def merge_watch_ignore_patterns(
    per_dir: Sequence[str],
    global_patterns: Sequence[str],
) -> tuple[str, ...]:
    """Merge per-watch-dir and global ignore globs; per-dir entries take precedence."""
    seen: set[str] = set()
    merged: list[str] = []
    for pattern in (*per_dir, *global_patterns):
        text = str(pattern).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
    return tuple(merged)


def _coerce_ignore_patterns(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return tuple(DEFAULT_WATCH_DIR_IGNORE_PATTERNS)
    patterns = tuple(str(p) for p in raw if p)
    return patterns or tuple(DEFAULT_WATCH_DIR_IGNORE_PATTERNS)


def default_watch_dir_settings(*, deleted: bool = False) -> WatchDirSettings:
    """Return default settings (used when creating a new ``settings.json``)."""
    return WatchDirSettings(
        deleted=deleted,
        ignore_patterns=tuple(DEFAULT_WATCH_DIR_IGNORE_PATTERNS),
    )


def load_watch_dir_settings(watch_dir: Path) -> WatchDirSettings:
    """Load settings from ``watch_dir/settings.json``; missing keys use defaults."""
    path = _settings_path(watch_dir)
    if not path.is_file():
        return default_watch_dir_settings()
    if not is_readable_file(path, log=logger):
        return default_watch_dir_settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Invalid %s: %s; using defaults", path, exc)
        return default_watch_dir_settings()
    if not isinstance(raw, dict):
        return default_watch_dir_settings()
    deleted = bool(raw.get("deleted", False))
    ignore_patterns = _coerce_ignore_patterns(raw.get("ignore_patterns"))
    return WatchDirSettings(deleted=deleted, ignore_patterns=ignore_patterns)


def write_watch_dir_settings(watch_dir: Path, settings: WatchDirSettings) -> bool:
    """Atomically write ``settings.json`` under ``watch_dir``.

    Returns ``True`` on success. When ``watch_dir`` is not writable by the
    current process (e.g. a root-owned watch directory under an unprivileged
    service account), this logs a ``[FS_PERM]`` error and returns ``False``
    instead of raising, so one inaccessible watch directory does not abort the
    whole settings sync / reload cycle.
    """
    try:
        watch_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error(
            "[FS_PERM] cannot create watch directory %s: %s; skipping settings write",
            watch_dir,
            exc,
        )
        return False
    if not is_writable_dir(watch_dir, log=logger):
        return False
    path = _settings_path(watch_dir)
    payload = {
        "deleted": settings.deleted,
        "ignore_patterns": list(settings.ignore_patterns),
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=".settings.",
            suffix=".json",
            dir=str(watch_dir),
        )
    except OSError as exc:
        logger.error(
            "[FS_PERM] cannot create settings temp file in %s: %s; skipping",
            watch_dir,
            exc,
        )
        return False
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
        return True
    except OSError as exc:
        logger.error("Failed to write %s: %s; skipping", path, exc)
        return False
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def ensure_watch_dir_settings(watch_dir: Path) -> WatchDirSettings:
    """Create ``settings.json`` with defaults when missing; return loaded settings."""
    path = _settings_path(watch_dir)
    if not path.is_file():
        settings = default_watch_dir_settings(deleted=False)
        write_watch_dir_settings(watch_dir, settings)
        return settings
    return load_watch_dir_settings(watch_dir)
