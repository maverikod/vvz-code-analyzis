"""Tests for json_get_node_info parameter validation."""

from __future__ import annotations

import uuid

import pytest

from code_analysis.commands.json_get_node_info_command import JsonGetNodeInfoCommand
from code_analysis.core.exceptions import ValidationError


@pytest.fixture
def cmd() -> JsonGetNodeInfoCommand:
    return JsonGetNodeInfoCommand()


@pytest.fixture
def tree_id() -> str:
    return str(uuid.uuid4())


def test_validate_params_accepts_node_id(
    cmd: JsonGetNodeInfoCommand, tree_id: str
) -> None:
    node_id = str(uuid.uuid4())
    out = cmd.validate_params({"tree_id": tree_id, "node_id": node_id})
    assert out["node_id"] == node_id


def test_validate_params_accepts_json_pointer(
    cmd: JsonGetNodeInfoCommand, tree_id: str
) -> None:
    out = cmd.validate_params({"tree_id": tree_id, "json_pointer": "/items/0"})
    assert out["json_pointer"] == "/items/0"


def test_validate_params_accepts_json_pointer_empty_string(
    cmd: JsonGetNodeInfoCommand, tree_id: str
) -> None:
    out = cmd.validate_params({"tree_id": tree_id, "json_pointer": ""})
    assert out["json_pointer"] == ""


def test_validate_params_accepts_key_path_string(
    cmd: JsonGetNodeInfoCommand, tree_id: str
) -> None:
    out = cmd.validate_params({"tree_id": tree_id, "key_path": "items.0"})
    assert out["key_path"] == "items.0"


def test_validate_params_accepts_key_path_string_array(
    cmd: JsonGetNodeInfoCommand, tree_id: str
) -> None:
    out = cmd.validate_params({"tree_id": tree_id, "key_path": ["items", "0"]})
    assert out["key_path"] == ["items", "0"]


def test_validate_params_accepts_node_id_with_json_pointer(
    cmd: JsonGetNodeInfoCommand, tree_id: str
) -> None:
    node_id = str(uuid.uuid4())
    out = cmd.validate_params(
        {
            "tree_id": tree_id,
            "node_id": node_id,
            "json_pointer": "/items/0",
        }
    )
    assert out["node_id"] == node_id
    assert out["json_pointer"] == "/items/0"


def test_validate_params_rejects_tree_id_only(
    cmd: JsonGetNodeInfoCommand, tree_id: str
) -> None:
    with pytest.raises(
        ValidationError, match="node_id, json_pointer, key_path"
    ) as exc_info:
        cmd.validate_params({"tree_id": tree_id})
    assert exc_info.value.field == "node_id"


@pytest.mark.parametrize("bad_key_path", [42, True, {"a": "b"}, 3.14])
def test_validate_params_rejects_key_path_non_string_non_array(
    cmd: JsonGetNodeInfoCommand,
    tree_id: str,
    bad_key_path: object,
) -> None:
    with pytest.raises(ValidationError, match="key_path") as exc_info:
        cmd.validate_params({"tree_id": tree_id, "key_path": bad_key_path})
    assert exc_info.value.field == "key_path"


@pytest.mark.parametrize(
    "bad_key_path",
    [["items", 0], [1, "two"], ["a", None]],
)
def test_validate_params_rejects_key_path_array_with_non_string_items(
    cmd: JsonGetNodeInfoCommand,
    tree_id: str,
    bad_key_path: list[object],
) -> None:
    with pytest.raises(ValidationError, match="key_path") as exc_info:
        cmd.validate_params({"tree_id": tree_id, "key_path": bad_key_path})
    assert exc_info.value.field == "key_path"


def test_validate_params_rejects_unknown_param(
    cmd: JsonGetNodeInfoCommand, tree_id: str
) -> None:
    with pytest.raises(ValidationError, match="unknown parameter"):
        cmd.validate_params(
            {
                "tree_id": tree_id,
                "node_id": str(uuid.uuid4()),
                "__unknown_param__": True,
            }
        )
