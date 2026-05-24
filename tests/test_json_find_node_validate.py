"""Tests for json_find_node parameter validation."""

from __future__ import annotations

import uuid

import pytest

from code_analysis.commands.json_find_node_command import JsonFindNodeCommand
from code_analysis.core.exceptions import ValidationError


@pytest.fixture
def cmd() -> JsonFindNodeCommand:
    return JsonFindNodeCommand()


@pytest.fixture
def tree_id() -> str:
    return str(uuid.uuid4())


def test_validate_params_accepts_json_pointer(
    cmd: JsonFindNodeCommand, tree_id: str
) -> None:
    out = cmd.validate_params({"tree_id": tree_id, "json_pointer": "/items/0"})
    assert out["json_pointer"] == "/items/0"


def test_validate_params_accepts_key_path_string(
    cmd: JsonFindNodeCommand, tree_id: str
) -> None:
    out = cmd.validate_params({"tree_id": tree_id, "key_path": "items.0"})
    assert out["key_path"] == "items.0"


def test_validate_params_accepts_key_path_string_array(
    cmd: JsonFindNodeCommand, tree_id: str
) -> None:
    out = cmd.validate_params({"tree_id": tree_id, "key_path": ["items", "0"]})
    assert out["key_path"] == ["items", "0"]


def test_validate_params_accepts_json_pointer_and_key_path(
    cmd: JsonFindNodeCommand, tree_id: str
) -> None:
    out = cmd.validate_params(
        {
            "tree_id": tree_id,
            "json_pointer": "/items/0",
            "key_path": "items.0",
        }
    )
    assert out["json_pointer"] == "/items/0"
    assert out["key_path"] == "items.0"


def test_validate_params_rejects_tree_id_only(
    cmd: JsonFindNodeCommand, tree_id: str
) -> None:
    with pytest.raises(
        ValidationError, match="json_pointer and/or key_path"
    ) as exc_info:
        cmd.validate_params({"tree_id": tree_id})
    assert exc_info.value.field == "json_pointer"


@pytest.mark.parametrize("bad_key_path", [42, True, {"a": "b"}, 3.14])
def test_validate_params_rejects_key_path_non_string_non_array(
    cmd: JsonFindNodeCommand,
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
    cmd: JsonFindNodeCommand,
    tree_id: str,
    bad_key_path: list[object],
) -> None:
    with pytest.raises(ValidationError, match="key_path") as exc_info:
        cmd.validate_params({"tree_id": tree_id, "key_path": bad_key_path})
    assert exc_info.value.field == "key_path"


def test_validate_params_rejects_unknown_param(
    cmd: JsonFindNodeCommand, tree_id: str
) -> None:
    with pytest.raises(ValidationError, match="unknown parameter"):
        cmd.validate_params(
            {
                "tree_id": tree_id,
                "json_pointer": "/a",
                "__unknown_param__": True,
            }
        )
