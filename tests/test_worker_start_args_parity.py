"""
Boot-parity worker start-argument tests (bug 827e2b05).

``StartWorkerMCPCommand.execute`` (manual ``start_worker``) used to build its
own ad-hoc kwargs for ``WorkerManager.start_*_worker``, diverging from what
the server computes at boot (``code_analysis/main_workers.py``). The clearest
observable case: for vectorization, manual passed the ENTIRE
``code_analysis`` config section unfiltered into ``ServerConfig(**...)``.
``ServerConfig`` has ``model_config = {"extra": "forbid"}`` and any real
config carries a ``database`` key (and a ``storage`` key) that are not
``ServerConfig`` fields, so this deterministically raised a pydantic
``ValidationError`` that manual's ``except Exception`` swallowed into
``svo_config = None`` -- the worker could chunk but never embed. It also
defaulted ``worker_log_path`` under the passed project root instead of
``storage.log_dir`` (boot's location), so a manually-started worker's PID
file lived at a different path than a boot-started one for the same
project -- the only dedup guard (see ``core/worker_registry.py``) is a PID
file keyed on that path, so manual+boot workers could coexist on the same DB.

``test_manual_start_vectorization_worker_kwargs_match_boot`` captures exactly
what ``StartWorkerMCPCommand.execute`` passes to
``WorkerManager.start_vectorization_worker`` (mocked) against a realistic
config fixture (mirrors ``packaging/config.json.template``, ``database`` key
included). Pre-fix this failed both assertions (log path under the project
root, ``svo_config`` is ``None``); post-fix (``code_analysis.core.worker_start_args``
resolvers, ported verbatim from ``main_workers.py`` boot logic) both hold.

The remaining tests exercise ``code_analysis.core.worker_start_args``
resolvers directly: svo_config survives extra config keys, the
``indexing_worker.enabled=false`` kill-switch is honored (a switch manual
never even read before this fix), explicit overrides win over config values,
omitted overrides keep config values, and log paths for all three worker
types land under ``storage.log_dir`` like boot -- never under a passed
project root.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from code_analysis.commands.start_worker_mcp_command import StartWorkerMCPCommand
from code_analysis.core.worker_start_args import (
    WorkerStartPlan,
    resolve_file_watcher_worker_kwargs,
    resolve_indexing_worker_kwargs,
    resolve_vectorization_worker_kwargs,
)


def _realistic_config_data(storage_root: Path) -> Dict[str, Any]:
    """Config dict shaped like ``packaging/config.json.template`` (has a
    ``database`` key and a ``storage`` key -- neither is a ``ServerConfig``
    field; a config lacking them would not reproduce the bug)."""
    return {
        "server": {"log_dir": str(storage_root / "logs")},
        "code_analysis": {
            "host": "0.0.0.0",
            "port": 15010,
            "vector_search_backend": "auto",
            "storage": {
                "db_path": str(storage_root / "data" / "code_analysis.db"),
                "faiss_dir": str(storage_root / "faiss"),
                "locks_dir": str(storage_root / "locks"),
                "backup_dir": str(storage_root / "backups"),
                "trash_dir": str(storage_root / "trash"),
            },
            "database": {
                "driver": {
                    "type": "postgres",
                    "config": {
                        "host": "127.0.0.1",
                        "port": 5432,
                        "dbname": "code_analysis",
                        "user": "code_analysis",
                        "password_env": "CODE_ANALYSIS_POSTGRES_PASSWORD",
                    },
                },
                "rpc": {"shm_threshold_bytes": 65536, "shm_enabled": True},
            },
            "vector_dim": 1024,
            "chunker": {
                "enabled": True,
                "url": "svo-chunker",
                "port": 8009,
                "protocol": "https",
            },
            "embedding": {
                "enabled": True,
                "host": "embed",
                "port": 8001,
                "protocol": "https",
            },
            "worker": {
                "enabled": True,
                "poll_interval": 30,
                "batch_size": 5,
                "log_path": str(storage_root / "logs" / "vectorization_worker.log"),
            },
            "file_watcher": {
                "enabled": True,
                "scan_interval": 60,
                "log_path": str(storage_root / "logs" / "file_watcher.log"),
                "version_dir": str(storage_root / "versions"),
                "ignore_patterns": ["**/.git/**"],
            },
            "indexing_worker": {
                "enabled": True,
                "poll_interval": 30,
                "batch_size": 5,
                "log_path": str(storage_root / "logs" / "indexing_worker.log"),
            },
            "github": {"timeout_seconds": 30},
            "search_session": {"ttl_seconds": 1800},
        },
    }


def _write_config(tmp_path: Path) -> Path:
    """Write a realistic config.json fixture to disk and return its path."""
    storage_root = tmp_path / "state"
    config_data = _realistic_config_data(storage_root)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_data), encoding="utf-8")
    return config_path


class _FakeWorkerManager:
    """Captures kwargs passed to start_*_worker instead of spawning a process."""

    def __init__(self) -> None:
        self.calls: Dict[str, Dict[str, Any]] = {}

    def _record(self, name: str, kwargs: Dict[str, Any]) -> Any:
        self.calls[name] = kwargs

        class _Result:
            success = True
            worker_type = name
            pid = 12345
            message = "started (fake)"
            __dict__ = {
                "success": True,
                "worker_type": name,
                "pid": 12345,
                "message": "started (fake)",
            }

        return _Result()

    def start_vectorization_worker(self, **kwargs: Any) -> Any:
        """Record kwargs for a vectorization worker start call."""
        return self._record("vectorization", kwargs)

    def start_file_watcher_worker(self, **kwargs: Any) -> Any:
        """Record kwargs for a file_watcher worker start call."""
        return self._record("file_watcher", kwargs)

    def start_indexing_worker(self, **kwargs: Any) -> Any:
        """Record kwargs for an indexing worker start call."""
        return self._record("indexing", kwargs)


@pytest.mark.asyncio
async def test_manual_start_vectorization_worker_kwargs_match_boot(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Manual start_worker(vectorization) must resolve boot-parity kwargs.

    worker_log_path must land under storage.log_dir (never under the passed
    project root), and svo_config must not be None -- the chunker must survive
    despite the config carrying a ``database`` key ServerConfig rejects when
    passed unfiltered (the exact mechanism of bug 827e2b05).
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    config_path = _write_config(tmp_path)

    fake_manager = _FakeWorkerManager()
    monkeypatch.setattr(
        StartWorkerMCPCommand,
        "_resolve_project_root",
        staticmethod(lambda project_id: project_root),
    )
    monkeypatch.setattr(
        StartWorkerMCPCommand,
        "_resolve_config_path",
        staticmethod(lambda: config_path),
    )
    monkeypatch.setattr(
        "code_analysis.commands.start_worker_mcp_command.get_worker_manager",
        lambda: fake_manager,
    )

    cmd = StartWorkerMCPCommand()
    result = await cmd.execute(
        worker_type="vectorization", project_id="fixture-project-id"
    )

    assert getattr(result, "success", None) is not False, getattr(
        result, "message", result
    )
    assert "vectorization" in fake_manager.calls, (
        "start_vectorization_worker was never called "
        f"(command returned {result!r} instead)"
    )
    kwargs = fake_manager.calls["vectorization"]

    expected_log_dir = str((tmp_path / "state" / "logs").resolve())
    actual_log_path = kwargs.get("worker_log_path") or ""
    assert actual_log_path.startswith(expected_log_dir), (
        f"worker_log_path={actual_log_path!r} must live under storage.log_dir "
        f"({expected_log_dir!r}), like boot -- not under the passed project "
        f"root ({project_root!r})"
    )
    assert str(project_root) not in actual_log_path, (
        f"worker_log_path={actual_log_path!r} must not be derived from the "
        f"passed project root ({project_root!r})"
    )
    assert kwargs.get("svo_config") is not None, (
        "svo_config must not be None: the realistic config fixture has a "
        "'database' key ServerConfig rejects when the whole code_analysis "
        "section is passed unfiltered (bug 827e2b05 mechanism)"
    )
    assert kwargs["svo_config"].get("chunker"), (
        f"svo_config must carry the configured chunker, got {kwargs['svo_config'].get('chunker')!r}"
    )


class TestResolveVectorizationWorkerKwargs:
    """Direct unit tests for resolve_vectorization_worker_kwargs."""

    def test_svo_config_survives_extra_config_keys(self, tmp_path: Path) -> None:
        """A 'database'/'storage'/'github' key in code_analysis must not
        blank out svo_config (must not raise, must not silently skip)."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_vectorization_worker_kwargs(config_data, config_path)

        assert plan.ok is True, plan.skip_reason
        assert plan.kwargs is not None
        assert plan.kwargs["svo_config"] is not None
        assert plan.kwargs["svo_config"].get("chunker")

    def test_worker_disabled_kill_switch(self, tmp_path: Path) -> None:
        """worker.enabled=false must produce a not-ok plan with a reason."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        config_data["code_analysis"]["worker"]["enabled"] = False
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_vectorization_worker_kwargs(config_data, config_path)

        assert plan.ok is False
        assert plan.kwargs is None
        assert plan.skip_reason
        assert "disabled" in plan.skip_reason

    def test_no_chunker_configured(self, tmp_path: Path) -> None:
        """Missing chunker config must produce a structured skip, not a crash."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        del config_data["code_analysis"]["chunker"]
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_vectorization_worker_kwargs(config_data, config_path)

        assert plan.ok is False
        assert plan.skip_reason and "chunker" in plan.skip_reason

    def test_overrides_win_over_config(self, tmp_path: Path) -> None:
        """Explicitly passed overrides must win over config-derived values."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_vectorization_worker_kwargs(
            config_data,
            config_path,
            overrides={"batch_size": 999, "poll_interval": 7, "vector_dim": 42},
        )

        assert plan.ok is True, plan.skip_reason
        assert plan.kwargs["batch_size"] == 999
        assert plan.kwargs["poll_interval"] == 7
        assert plan.kwargs["vector_dim"] == 42

    def test_omitted_overrides_keep_config_values(self, tmp_path: Path) -> None:
        """Overrides absent from the dict must not clobber config values."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_vectorization_worker_kwargs(
            config_data, config_path, overrides={"batch_size": 999}
        )

        assert plan.ok is True, plan.skip_reason
        assert plan.kwargs["batch_size"] == 999
        assert plan.kwargs["poll_interval"] == 30  # from config, untouched
        assert plan.kwargs["vector_dim"] == 1024  # from config, untouched

    def test_log_path_under_storage_log_dir(self, tmp_path: Path) -> None:
        """worker_log_path (config-driven) must resolve under storage.log_dir."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        # Drop the configured log_path so the boot-parity default kicks in.
        del config_data["code_analysis"]["worker"]["log_path"]
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_vectorization_worker_kwargs(config_data, config_path)

        assert plan.ok is True, plan.skip_reason
        expected = str((storage_root / "logs" / "vectorization_worker.log").resolve())
        assert plan.kwargs["worker_log_path"] == expected


class TestResolveIndexingWorkerKwargs:
    """Direct unit tests for resolve_indexing_worker_kwargs."""

    def test_disabled_kill_switch(self, tmp_path: Path) -> None:
        """indexing_worker.enabled=false must skip (manual never checked this)."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        config_data["code_analysis"]["indexing_worker"]["enabled"] = False
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_indexing_worker_kwargs(config_data, config_path)

        assert plan.ok is False
        assert plan.skip_reason and "disabled" in plan.skip_reason

    def test_default_batch_size_matches_boot_not_manual(self, tmp_path: Path) -> None:
        """Default batch_size must be boot's 5, not manual's old hardcoded 10."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        del config_data["code_analysis"]["indexing_worker"]["batch_size"]
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_indexing_worker_kwargs(config_data, config_path)

        assert plan.ok is True, plan.skip_reason
        assert plan.kwargs["batch_size"] == 5

    def test_overrides_win(self, tmp_path: Path) -> None:
        """Explicit overrides must win for indexing too."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_indexing_worker_kwargs(
            config_data, config_path, overrides={"batch_size": 3}
        )

        assert plan.ok is True, plan.skip_reason
        assert plan.kwargs["batch_size"] == 3
        assert plan.kwargs["poll_interval"] == 30

    def test_log_path_under_storage_log_dir(self, tmp_path: Path) -> None:
        """worker_log_path default must resolve under storage.log_dir."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        del config_data["code_analysis"]["indexing_worker"]["log_path"]
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_indexing_worker_kwargs(config_data, config_path)

        assert plan.ok is True, plan.skip_reason
        expected = str((storage_root / "logs" / "indexing_worker.log").resolve())
        assert plan.kwargs["worker_log_path"] == expected


class TestResolveFileWatcherWorkerKwargs:
    """Direct unit tests for resolve_file_watcher_worker_kwargs."""

    def test_disabled_kill_switch(self, tmp_path: Path) -> None:
        """file_watcher.enabled=false must skip."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        config_data["code_analysis"]["file_watcher"]["enabled"] = False
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_file_watcher_worker_kwargs(config_data, config_path)

        assert plan.ok is False
        assert plan.skip_reason and "disabled" in plan.skip_reason

    def test_log_path_under_storage_log_dir(self, tmp_path: Path) -> None:
        """worker_log_path default must resolve under storage.log_dir."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        del config_data["code_analysis"]["file_watcher"]["log_path"]
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_file_watcher_worker_kwargs(config_data, config_path)

        assert plan.ok is True, plan.skip_reason
        expected = str((storage_root / "logs" / "file_watcher.log").resolve())
        assert plan.kwargs["worker_log_path"] == expected

    def test_version_dir_is_absolute(self, tmp_path: Path) -> None:
        """version_dir must be resolved to an absolute path (boot-parity)."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        config_data["code_analysis"]["file_watcher"]["version_dir"] = "data/versions"
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_file_watcher_worker_kwargs(config_data, config_path)

        assert plan.ok is True, plan.skip_reason
        assert Path(plan.kwargs["version_dir"]).is_absolute()

    def test_watch_dirs_override_wins(self, tmp_path: Path) -> None:
        """An explicit watch_dirs override (project-root default) must win
        over config-driven discovery."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")
        override_dirs = [{"path": "/some/project/root", "id": "/some/project/root"}]

        plan = resolve_file_watcher_worker_kwargs(
            config_data, config_path, overrides={"watch_dirs": override_dirs}
        )

        assert plan.ok is True, plan.skip_reason
        assert plan.kwargs["watch_dirs"] == override_dirs

    def test_ignore_patterns_config_driven(self, tmp_path: Path) -> None:
        """ignore_patterns must come from config, matching boot."""
        storage_root = tmp_path / "state"
        config_data = _realistic_config_data(storage_root)
        config_data["code_analysis"]["file_watcher"]["ignore_patterns"] = [
            "**/only_this/**"
        ]
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        plan = resolve_file_watcher_worker_kwargs(config_data, config_path)

        assert plan.ok is True, plan.skip_reason
        assert plan.kwargs["ignore_patterns"] == ["**/only_this/**"]
