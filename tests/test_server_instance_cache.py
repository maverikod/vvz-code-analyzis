"""
Tests for the process-lifetime memoized ``get_server_instance_id`` (bug 9f5d860e).

Without memoization, the config-file branch re-parses ``config.json`` (commentjson +
lark grammar) on every call; this function is invoked once per project per
file-watcher scan cycle (plus many other per-request call sites), which was
observed as a config-reparse storm and 100% CPU, amplified per-project-per-cycle.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Iterator

import pytest

from code_analysis.core import server_instance as mod

# tests/conftest.py installs a SUITE-WIDE autouse fixture that monkeypatches
# ``code_analysis.core.server_instance.get_server_instance_id`` itself (to a
# fixed-partition-key stub, so every other test's DB queries stay on one
# server_instance_id). This module tests the REAL implementation, so capture
# the genuine function object at collection time — before any fixture has run
# — and restore it via monkeypatch inside our own autouse fixture (which runs
# after conftest's, since it is declared "closer" to these tests).
_REAL_GET_SERVER_INSTANCE_ID = mod.get_server_instance_id


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Restore the real implementation and reset the cache around each test."""
    monkeypatch.setattr(mod, "get_server_instance_id", _REAL_GET_SERVER_INSTANCE_ID)
    mod.reset_server_instance_id_cache()
    yield
    mod.reset_server_instance_id_cache()


class _CountingLoader:
    """Stand-in for ``load_raw_config``: counts calls, returns a fixed config."""

    def __init__(self, sid: str = "sid-fixed-0001") -> None:
        """Initialize the instance."""
        self.calls = 0
        self.sid = sid

    def __call__(self, config_path: Any) -> Dict[str, Any]:
        """Record a call and return a config mapping with ``sid``."""
        self.calls += 1
        return {"registration": {"instance_uuid": self.sid}}


def test_repeated_calls_load_config_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    N calls with env unset -> exactly ONE disk load (green with the fix).

    The assert is a strict equality (== 1, not <= N) precisely so it fails on
    unfixed code: a naive re-parse-per-call implementation would drive
    ``loader.calls`` to 10 here, not 1 — this is the regression guard, not
    merely a tolerance check.
    """
    monkeypatch.delenv("CODE_ANALYSIS_SERVER_INSTANCE_ID", raising=False)
    loader = _CountingLoader()
    monkeypatch.setattr("code_analysis.core.storage_paths.load_raw_config", loader)

    results = [mod.get_server_instance_id() for _ in range(10)]

    assert loader.calls == 1
    assert results == ["sid-fixed-0001"] * 10
    diag = mod.get_server_instance_id_cache_diagnostics()
    assert diag["config_load_count"] == 1
    assert diag["cache_hit_count"] == 9


def test_explicit_config_argument_bypasses_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit ``config=`` argument always bypasses the cache (never loads, never caches)."""
    monkeypatch.delenv("CODE_ANALYSIS_SERVER_INSTANCE_ID", raising=False)
    loader = _CountingLoader()
    monkeypatch.setattr("code_analysis.core.storage_paths.load_raw_config", loader)

    explicit_config = {"registration": {"instance_uuid": "explicit-sid"}}
    for _ in range(5):
        assert mod.get_server_instance_id(config=explicit_config) == "explicit-sid"

    assert loader.calls == 0
    diag = mod.get_server_instance_id_cache_diagnostics()
    assert diag["config_load_count"] == 0
    assert diag["cache_hit_count"] == 0


def test_env_var_branch_never_loads_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """The env-var resolution path never touches disk / the cache."""
    monkeypatch.setenv("CODE_ANALYSIS_SERVER_INSTANCE_ID", "env-sid-9999")
    loader = _CountingLoader()
    monkeypatch.setattr("code_analysis.core.storage_paths.load_raw_config", loader)

    for _ in range(5):
        assert mod.get_server_instance_id() == "env-sid-9999"

    assert loader.calls == 0
    diag = mod.get_server_instance_id_cache_diagnostics()
    assert diag["config_load_count"] == 0
    assert diag["cache_hit_count"] == 0


def test_reset_hook_forces_fresh_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    """``reset_server_instance_id_cache()`` clears the cache so the next call reloads."""
    monkeypatch.delenv("CODE_ANALYSIS_SERVER_INSTANCE_ID", raising=False)
    loader = _CountingLoader()
    monkeypatch.setattr("code_analysis.core.storage_paths.load_raw_config", loader)

    assert mod.get_server_instance_id() == "sid-fixed-0001"
    assert mod.get_server_instance_id() == "sid-fixed-0001"
    assert loader.calls == 1

    mod.reset_server_instance_id_cache()

    assert mod.get_server_instance_id() == "sid-fixed-0001"
    assert loader.calls == 2
    diag = mod.get_server_instance_id_cache_diagnostics()
    assert diag["config_load_count"] == 1
    assert diag["cache_hit_count"] == 0


def test_missing_instance_uuid_raises_and_is_never_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty/missing instance_uuid raises and is never cached (retried next call)."""
    monkeypatch.delenv("CODE_ANALYSIS_SERVER_INSTANCE_ID", raising=False)

    calls = {"n": 0}

    def _empty_loader(config_path: Any) -> Dict[str, Any]:
        calls["n"] += 1
        return {"registration": {"instance_uuid": ""}}

    monkeypatch.setattr(
        "code_analysis.core.storage_paths.load_raw_config", _empty_loader
    )

    with pytest.raises(RuntimeError):
        mod.get_server_instance_id()
    with pytest.raises(RuntimeError):
        mod.get_server_instance_id()

    assert calls["n"] == 2
    diag = mod.get_server_instance_id_cache_diagnostics()
    assert diag["config_load_count"] == 0
