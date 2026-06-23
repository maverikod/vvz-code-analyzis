"""Tests for filesystem permission pre-checks and watcher skip-on-denial.

These run only as a non-root user: root bypasses POSIX permission bits, so the
denial paths cannot be exercised. They are skipped under uid 0.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from code_analysis.core.fs_permissions import (
    is_readable_dir,
    is_readable_file,
    is_writable_dir,
)
from code_analysis.core.watch_dir_settings import (
    default_watch_dir_settings,
    load_watch_dir_settings,
    write_watch_dir_settings,
)

_IS_ROOT = os.geteuid() == 0
_skip_as_root = pytest.mark.skipif(
    _IS_ROOT, reason="root bypasses POSIX permission bits"
)


def test_is_readable_dir_true_for_normal_dir(tmp_path: Path) -> None:
    assert is_readable_dir(tmp_path) is True


def test_is_writable_dir_true_for_normal_dir(tmp_path: Path) -> None:
    assert is_writable_dir(tmp_path) is True


def test_is_readable_file_true_for_normal_file(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert is_readable_file(f) is True


@_skip_as_root
def test_is_writable_dir_false_and_logs_on_denied(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)  # r-x: not writable
    try:
        with caplog.at_level(logging.ERROR):
            assert is_writable_dir(d) is False
        assert any("[FS_PERM]" in r.message for r in caplog.records)
    finally:
        d.chmod(0o700)


@_skip_as_root
def test_is_readable_file_false_on_denied(tmp_path: Path) -> None:
    f = tmp_path / "secret.txt"
    f.write_text("x", encoding="utf-8")
    f.chmod(0o000)
    try:
        assert is_readable_file(f) is False
    finally:
        f.chmod(0o600)


@_skip_as_root
def test_write_watch_dir_settings_skips_on_unwritable_dir(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A non-writable watch dir must not raise; it logs and returns False."""
    watch_dir = tmp_path / "wd"
    watch_dir.mkdir()
    watch_dir.chmod(0o500)
    try:
        with caplog.at_level(logging.ERROR):
            ok = write_watch_dir_settings(watch_dir, default_watch_dir_settings())
        assert ok is False
        assert not (watch_dir / "settings.json").exists()
        assert any("[FS_PERM]" in r.message for r in caplog.records)
    finally:
        watch_dir.chmod(0o700)


def test_write_then_load_watch_dir_settings_roundtrip(tmp_path: Path) -> None:
    watch_dir = tmp_path / "wd"
    watch_dir.mkdir()
    assert write_watch_dir_settings(watch_dir, default_watch_dir_settings()) is True
    loaded = load_watch_dir_settings(watch_dir)
    assert loaded.deleted is False


@_skip_as_root
def test_load_watch_dir_settings_defaults_on_unreadable_file(tmp_path: Path) -> None:
    watch_dir = tmp_path / "wd"
    watch_dir.mkdir()
    assert write_watch_dir_settings(watch_dir, default_watch_dir_settings()) is True
    (watch_dir / "settings.json").chmod(0o000)
    try:
        loaded = load_watch_dir_settings(watch_dir)
        # Falls back to defaults instead of raising.
        assert loaded == default_watch_dir_settings()
    finally:
        (watch_dir / "settings.json").chmod(0o600)
