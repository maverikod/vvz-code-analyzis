"""Tests for comment-aware config.json loading."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from code_analysis.core.config_json import (
    ConfigJSONDecodeError,
    install_comment_json_for_mcp_adapter,
    load_config_json,
    load_config_json_text,
)


def test_load_config_json_text_plain_json() -> None:
    """Verify test load config json text plain json."""
    data = load_config_json_text('{"server": {"port": 15000}}')
    assert data["server"]["port"] == 15000


def test_load_config_json_text_with_hash_comments() -> None:
    """Verify test load config json text with hash comments."""
    text = """
# deployment config
{
  "code_analysis": {
    "database": {
      "driver": {
        "config": {"port": 5433}
      }
    }
  }
}
"""
    data = load_config_json_text(text)
    assert data["code_analysis"]["database"]["driver"]["config"]["port"] == 5433


def test_load_config_json_text_rejects_non_object_root() -> None:
    """Verify test load config json text rejects non object root."""
    with pytest.raises(ConfigJSONDecodeError, match="JSON object"):
        load_config_json_text("[1, 2]")


def test_load_config_json_from_file(tmp_path: Path) -> None:
    """Verify test load config json from file."""
    path = tmp_path / "config.json"
    path.write_text(
        '# comment\n{"server": {"host": "127.0.0.1"}}\n',
        encoding="utf-8",
    )
    data = load_config_json(path)
    assert data["server"]["host"] == "127.0.0.1"


def _write_minimal_commented_config(path: Path) -> None:
    """Write a minimal SimpleConfig-compatible config.json with comments."""
    path.write_text(
        "# minimal test config\n"
        '{"server": {"host": "127.0.0.1", "port": 8000, "protocol": "http"}}\n',
        encoding="utf-8",
    )


def test_install_comment_json_does_not_touch_stdlib_json_loads(
    tmp_path: Path,
) -> None:
    """
    Regression guard for the global-state bug: ``json.loads`` on the stdlib
    ``json`` module must be the exact same object before, during, and after
    ``SimpleConfig.load()`` runs through the comment-JSON patch. The old
    implementation reassigned ``sc_mod.json.loads`` (an alias of the stdlib
    module) for the duration of the call; this asserts that can never
    happen again.
    """
    from mcp_proxy_adapter.core.config.simple_config import SimpleConfig

    original_loads = json.loads
    install_comment_json_for_mcp_adapter()
    assert json.loads is original_loads

    config_path = tmp_path / "config.json"
    _write_minimal_commented_config(config_path)

    model = SimpleConfig(str(config_path)).load()

    assert json.loads is original_loads
    assert model.server.host == "127.0.0.1"


def test_simple_config_load_end_to_end_with_comments(tmp_path: Path) -> None:
    """A config.json with ``#`` and ``//`` comments loads via SimpleConfig."""
    from mcp_proxy_adapter.core.config.simple_config import SimpleConfig

    install_comment_json_for_mcp_adapter()

    config_path = tmp_path / "config.json"
    config_path.write_text(
        "// top-level comment\n"
        "{\n"
        '  "server": {\n'
        '    "host": "127.0.0.1", // inline comment\n'
        '    "port": 9443,\n'
        '    "protocol": "https",\n'
        '    "servername": "example.test"\n'
        "    # trailing hash comment\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )

    model = SimpleConfig(str(config_path)).load()

    assert model.server.host == "127.0.0.1"
    assert model.server.port == 9443
    assert model.server.protocol == "https"
    assert model.server.servername == "example.test"


def test_simple_config_load_does_not_race_unrelated_json_load(
    tmp_path: Path,
) -> None:
    """
    Concurrency regression guard: race ``SimpleConfig.load()`` (commented
    config) against ``json.load()`` of a DIFFERENT, unrelated file on another
    thread. The unrelated read must always return its own file's real
    content and must never observe the config dict (which is what happened
    when the patch replaced the process-global ``json.loads``).
    """
    from mcp_proxy_adapter.core.config.simple_config import SimpleConfig

    install_comment_json_for_mcp_adapter()

    config_path = tmp_path / "config.json"
    _write_minimal_commented_config(config_path)

    other_path = tmp_path / "unrelated.json"
    other_content = {"unrelated": "sentinel_value_12345", "values": [1, 2, 3]}
    other_path.write_text(json.dumps(other_content), encoding="utf-8")

    iterations = 200
    start_barrier = threading.Barrier(2)
    mismatches: list[str] = []
    config_errors: list[BaseException] = []

    def load_config_repeatedly() -> None:
        start_barrier.wait()
        for _ in range(iterations):
            try:
                SimpleConfig(str(config_path)).load()
            except BaseException as exc:  # noqa: BLE001 - captured for assertion
                config_errors.append(exc)

    def load_unrelated_repeatedly() -> None:
        start_barrier.wait()
        for _ in range(iterations):
            with open(other_path, encoding="utf-8") as fh:
                data = json.load(fh)
            if data != other_content:
                mismatches.append(repr(data))

    config_thread = threading.Thread(target=load_config_repeatedly)
    unrelated_thread = threading.Thread(target=load_unrelated_repeatedly)
    config_thread.start()
    unrelated_thread.start()
    config_thread.join(timeout=60)
    unrelated_thread.join(timeout=60)

    assert not config_thread.is_alive(), "config-loading thread did not finish"
    assert not unrelated_thread.is_alive(), "unrelated-loading thread did not finish"
    assert config_errors == [], f"SimpleConfig.load() raised: {config_errors[:3]}"
    assert mismatches == [], (
        f"json.load() of the unrelated file returned wrong content "
        f"{len(mismatches)}/{iterations} times: {mismatches[:3]}"
    )
