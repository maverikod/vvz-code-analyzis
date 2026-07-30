"""Unit tests for code_analysis_client.schema_disk_cache (bug 8e6acb34, Fix 1)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis_client import CodeAnalysisAsyncClient
from code_analysis_client.schema_disk_cache import (
    clear_cached_schemas,
    load_cached_schema,
    store_cached_schema,
)

_BASE_URL = "https://example-server:15010"
_SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "integer"}},
    "required": [],
    "additionalProperties": False,
}


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every test in this module to a fresh, isolated cache directory."""
    cache_dir = tmp_path / "schema_cache"
    monkeypatch.setenv("CODE_ANALYSIS_CLIENT_SCHEMA_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("CODE_ANALYSIS_CLIENT_DISABLE_SCHEMA_CACHE", raising=False)
    monkeypatch.delenv("CODE_ANALYSIS_CLIENT_SCHEMA_CACHE_TTL_SECONDS", raising=False)
    return cache_dir


def test_store_then_load_round_trips() -> None:
    """Verify a stored schema is returned by a subsequent load for the same key."""
    assert load_cached_schema(_BASE_URL, "health") is None
    store_cached_schema(_BASE_URL, "health", _SCHEMA)
    assert load_cached_schema(_BASE_URL, "health") == _SCHEMA


def test_load_distinguishes_command_and_server() -> None:
    """Verify cache entries are keyed by (base_url, command), not shared across either."""
    store_cached_schema(_BASE_URL, "health", _SCHEMA)
    assert load_cached_schema(_BASE_URL, "list_projects") is None
    assert load_cached_schema("https://other-server:1", "health") is None


def test_load_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify an entry older than the configured TTL is treated as a miss."""
    monkeypatch.setenv("CODE_ANALYSIS_CLIENT_SCHEMA_CACHE_TTL_SECONDS", "0.05")
    store_cached_schema(_BASE_URL, "health", _SCHEMA)
    assert load_cached_schema(_BASE_URL, "health") == _SCHEMA
    time.sleep(0.1)
    assert load_cached_schema(_BASE_URL, "health") is None


def test_clear_cached_schemas_removes_entries() -> None:
    """Verify clear_cached_schemas deletes every entry for the given server."""
    store_cached_schema(_BASE_URL, "health", _SCHEMA)
    store_cached_schema(_BASE_URL, "list_projects", _SCHEMA)
    clear_cached_schemas(_BASE_URL)
    assert load_cached_schema(_BASE_URL, "health") is None
    assert load_cached_schema(_BASE_URL, "list_projects") is None


def test_disable_env_var_prevents_any_disk_io(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify the disable flag makes store/load pure no-ops and touches no files."""
    monkeypatch.setenv("CODE_ANALYSIS_CLIENT_DISABLE_SCHEMA_CACHE", "1")
    store_cached_schema(_BASE_URL, "health", _SCHEMA)
    assert load_cached_schema(_BASE_URL, "health") is None
    cache_dir = Path(
        __import__("os").environ["CODE_ANALYSIS_CLIENT_SCHEMA_CACHE_DIR"]
    )
    assert not cache_dir.exists()


def test_load_ignores_non_string_base_url() -> None:
    """Verify a non-string base_url (e.g. a MagicMock in unit tests) is a safe miss."""
    assert load_cached_schema(MagicMock(), "health") is None
    store_cached_schema(MagicMock(), "health", _SCHEMA)  # must not raise


def test_load_ignores_corrupt_cache_file(tmp_path: Path) -> None:
    """Verify a corrupted cache file on disk is treated as a miss, not an error."""
    store_cached_schema(_BASE_URL, "health", _SCHEMA)
    # Corrupt the file we just wrote.
    from code_analysis_client.schema_disk_cache import _entry_path

    path = _entry_path(_BASE_URL, "health")
    assert path is not None
    path.write_text("not json", encoding="utf-8")
    assert load_cached_schema(_BASE_URL, "health") is None


@pytest.mark.asyncio
async def test_client_get_command_schema_reuses_disk_cache_across_instances() -> None:
    """Verify a second client instance skips the network `help` call after the first warms the disk cache."""
    mock_rpc = MagicMock()
    mock_rpc.base_url = _BASE_URL
    mock_rpc.help = AsyncMock(
        return_value={"success": True, "data": {"schema": _SCHEMA, "metadata": {}}}
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        first = CodeAnalysisAsyncClient(host="h", port=1)
        schema1 = await first.get_command_schema("health")
        assert schema1 == _SCHEMA
        mock_rpc.help.assert_awaited_once_with("health")

        # A brand-new client instance -- its in-memory cache is empty, but the
        # on-disk cache warmed by `first` above should short-circuit the
        # network fetch entirely.
        second = CodeAnalysisAsyncClient(host="h", port=1)
        schema2 = await second.get_command_schema("health")
        assert schema2 == _SCHEMA
        mock_rpc.help.assert_awaited_once_with("health")  # still exactly once


@pytest.mark.asyncio
async def test_client_clear_command_schema_cache_purges_disk_entry() -> None:
    """Verify clear_command_schema_cache also forces the next fetch back to the network."""
    mock_rpc = MagicMock()
    mock_rpc.base_url = _BASE_URL
    mock_rpc.help = AsyncMock(
        return_value={"success": True, "data": {"schema": _SCHEMA, "metadata": {}}}
    )
    with patch(
        "code_analysis_client.client.JsonRpcClient",
        return_value=mock_rpc,
    ):
        client = CodeAnalysisAsyncClient(host="h", port=1)
        await client.get_command_schema("health")
        mock_rpc.help.assert_awaited_once_with("health")

        client.clear_command_schema_cache()

        another = CodeAnalysisAsyncClient(host="h", port=1)
        await another.get_command_schema("health")
        assert mock_rpc.help.await_count == 2
