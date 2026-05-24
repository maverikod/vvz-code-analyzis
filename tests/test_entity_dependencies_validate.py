"""Tests for get_entity_dependencies / get_entity_dependents parameter validation."""

from __future__ import annotations

import uuid
from typing import Any, Type, cast

import pytest

from code_analysis.commands.ast.entity_dependencies import (
    GetEntityDependenciesMCPCommand,
    GetEntityDependentsMCPCommand,
    _normalize_entity_id_param,
)
from code_analysis.core.exceptions import ValidationError


@pytest.fixture(params=[GetEntityDependenciesMCPCommand, GetEntityDependentsMCPCommand])
def cmd_class(
    request: pytest.FixtureRequest,
) -> Type[GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand]:
    return cast(
        Type[GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand],
        request.param,
    )


@pytest.fixture
def cmd(
    cmd_class: Type[GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand],
) -> GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand:
    return cmd_class()


@pytest.fixture
def base_params(
    cmd: GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand,
) -> dict[str, object]:
    entity_type = "function" if cmd.name == "get_entity_dependencies" else "class"
    return {"project_id": str(uuid.uuid4()), "entity_type": entity_type}


def test_validate_params_accepts_string_entity_id(
    cmd: GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand,
    base_params: dict[str, object],
) -> None:
    entity_id = str(uuid.uuid4())
    out = cmd.validate_params({**base_params, "entity_id": entity_id})
    assert out["entity_id"] == entity_id


def test_validate_params_accepts_integer_entity_id(
    cmd: GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand,
    base_params: dict[str, object],
) -> None:
    out = cmd.validate_params({**base_params, "entity_id": 42})
    assert out["entity_id"] == 42


def test_validate_params_accepts_entity_name_without_entity_id(
    cmd: GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand,
    base_params: dict[str, object],
) -> None:
    out = cmd.validate_params({**base_params, "entity_name": "my_func"})
    assert out["entity_name"] == "my_func"


@pytest.mark.parametrize(
    "entity_id",
    [
        True,
        False,
        1.5,
        [],
        {},
        {"id": 1},
    ],
)
def test_validate_params_rejects_invalid_entity_id_types(
    cmd: GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand,
    base_params: dict[str, object],
    entity_id: Any,
) -> None:
    with pytest.raises(ValidationError, match="entity_id") as exc_info:
        cmd.validate_params({**base_params, "entity_id": entity_id})
    assert exc_info.value.field == "entity_id"


@pytest.mark.parametrize("entity_id", ["", "   "])
def test_validate_params_rejects_blank_entity_id_without_entity_name(
    cmd: GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand,
    base_params: dict[str, object],
    entity_id: str,
) -> None:
    with pytest.raises(ValidationError, match="entity_id") as exc_info:
        cmd.validate_params({**base_params, "entity_id": entity_id})
    assert exc_info.value.field == "entity_id"


def test_validate_params_requires_entity_id_or_entity_name(
    cmd: GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand,
    base_params: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="entity_id or entity_name") as exc_info:
        cmd.validate_params(base_params)
    assert exc_info.value.field == "entity_id"


def test_validate_params_rejects_unknown_param(
    cmd: GetEntityDependenciesMCPCommand | GetEntityDependentsMCPCommand,
    base_params: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        cmd.validate_params(
            {**base_params, "entity_id": str(uuid.uuid4()), "__unknown_param__": True}
        )


@pytest.mark.parametrize(
    "normalizer_input,expected",
    [
        (None, None),
        (42, 42),
        ("  abc  ", "abc"),
    ],
)
def test_normalize_entity_id_param_accepts_valid_values(
    normalizer_input: Any,
    expected: Any,
) -> None:
    assert _normalize_entity_id_param(normalizer_input, command_name="test") == expected


@pytest.mark.parametrize(
    "normalizer_input",
    [True, False, 1.5, [], {}, {"id": 1}],
)
def test_normalize_entity_id_param_rejects_invalid_types(
    normalizer_input: Any,
) -> None:
    with pytest.raises(ValidationError, match="entity_id"):
        _normalize_entity_id_param(normalizer_input, command_name="test")
