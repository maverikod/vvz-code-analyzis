"""
Tests for BaseMCPCommand schema validation: unknown-key rejection.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from mcp_proxy_adapter.commands.result import CommandResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.project_management_mcp_commands.create_project import (
    CreateProjectMCPCommand,
)
from code_analysis.core.exceptions import ValidationError

_STRICT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "known": {"type": "string"},
    },
    "required": [],
    "additionalProperties": False,
}


class _StrictSchemaCommand(BaseMCPCommand):
    """Minimal command with additionalProperties: false for regression tests."""

    name = "strict_schema_test"
    version = "1.0.0"
    descr = "Test command for unknown-key rejection."
    category = "test"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return _STRICT_SCHEMA

    async def execute(self, **kwargs: Any) -> CommandResult:
        return SuccessResult(data={})


class TestValidateParamsAgainstSchemaUnknownKey:
    """Direct server-side validate_params_against_schema unknown-key rejection."""

    def test_rejects_unknown_key_when_additional_properties_false(self) -> None:
        with pytest.raises(ValidationError, match="unknown parameter") as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"known": "ok", "surprise": 1},
                _STRICT_SCHEMA,
                "strict_schema_test",
            )
        err = exc_info.value
        assert err.field == "surprise"
        assert err.code == "VALIDATION_ERROR"
        assert err.details == {"allowed": ["known"]}
        assert "Only schema-defined properties are allowed" in err.message


class TestBaseMCPCommandValidateParamsUnknownKey:
    """BaseMCPCommand.validate_params rejects unknown keys via schema."""

    def test_subclass_validate_params_rejects_unknown_key(self) -> None:
        with pytest.raises(ValidationError, match="unknown parameter") as exc_info:
            _StrictSchemaCommand().validate_params({"known": "ok", "unexpected": True})
        err = exc_info.value
        assert err.field == "unexpected"
        assert err.details == {"allowed": ["known"]}


class TestCreateProjectValidateParamsUnknownKey:
    """CreateProjectMCPCommand rejects unknown keys after SYS-004 fix."""

    def test_rejects_unknown_key_before_watch_dir_lookup(self) -> None:
        params = {
            "watch_dir_id": "550e8400-e29b-41d4-a716-446655440000",
            "project_name": "demo",
            "description": "demo project",
            "extra_param": "not in schema",
        }
        with pytest.raises(ValidationError, match="unknown parameter") as exc_info:
            CreateProjectMCPCommand().validate_params(params)
        err = exc_info.value
        assert err.field == "extra_param"
        assert "create_project" in err.message
        assert "allowed" in err.details


_EXTENDED_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "count": {"type": "integer", "minimum": 1, "maximum": 100},
        "ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "mode": {"type": "string", "enum": ["fast", "slow"]},
        "tags": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {"type": "string"},
        },
        "scores": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 10},
        },
    },
    "required": [],
    "additionalProperties": False,
}


class TestValidateParamsAgainstSchemaConstraints:
    """SYS-006: min/max, enum, array bounds, and item type validation."""

    def test_integer_minimum_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be >=") as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"count": 0},
                _EXTENDED_SCHEMA,
                "extended_test",
            )
        assert exc_info.value.field == "count"
        assert exc_info.value.details["minimum"] == 1

    def test_integer_maximum_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be <=") as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"count": 101},
                _EXTENDED_SCHEMA,
                "extended_test",
            )
        assert exc_info.value.field == "count"
        assert exc_info.value.details["maximum"] == 100

    def test_integer_within_bounds_accepted(self) -> None:
        BaseMCPCommand.validate_params_against_schema(
            {"count": 50},
            _EXTENDED_SCHEMA,
            "extended_test",
        )

    def test_number_minimum_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be >=") as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"ratio": -0.1},
                _EXTENDED_SCHEMA,
                "extended_test",
            )
        assert exc_info.value.field == "ratio"

    def test_number_maximum_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be <=") as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"ratio": 1.5},
                _EXTENDED_SCHEMA,
                "extended_test",
            )
        assert exc_info.value.field == "ratio"

    def test_number_within_bounds_accepted(self) -> None:
        BaseMCPCommand.validate_params_against_schema(
            {"ratio": 0.5},
            _EXTENDED_SCHEMA,
            "extended_test",
        )

    def test_enum_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be one of") as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"mode": "medium"},
                _EXTENDED_SCHEMA,
                "extended_test",
            )
        assert exc_info.value.field == "mode"
        assert exc_info.value.details["enum"] == ["fast", "slow"]

    def test_enum_accepted(self) -> None:
        BaseMCPCommand.validate_params_against_schema(
            {"mode": "fast"},
            _EXTENDED_SCHEMA,
            "extended_test",
        )

    def test_array_min_items_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at least 1 items") as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"tags": []},
                _EXTENDED_SCHEMA,
                "extended_test",
            )
        assert exc_info.value.field == "tags"
        assert exc_info.value.details["minItems"] == 1

    def test_array_max_items_rejected(self) -> None:
        with pytest.raises(ValidationError, match="at most 3 items") as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"tags": ["a", "b", "c", "d"]},
                _EXTENDED_SCHEMA,
                "extended_test",
            )
        assert exc_info.value.field == "tags"
        assert exc_info.value.details["maxItems"] == 3

    def test_array_item_type_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be string") as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"tags": ["ok", 42]},
                _EXTENDED_SCHEMA,
                "extended_test",
            )
        assert exc_info.value.field == "tags[1]"

    def test_array_item_min_max_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be <=") as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"scores": [5, 11]},
                _EXTENDED_SCHEMA,
                "extended_test",
            )
        assert exc_info.value.field == "scores[1]"

    def test_array_valid_items_accepted(self) -> None:
        BaseMCPCommand.validate_params_against_schema(
            {"tags": ["alpha", "beta"], "scores": [0, 10]},
            _EXTENDED_SCHEMA,
            "extended_test",
        )


_UNION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "flexible": {
            "anyOf": [
                {"type": "string"},
                {"type": "integer"},
            ],
        },
        "selector": {
            "oneOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "integer"}},
                {"type": "array", "items": {"type": "string"}},
            ],
        },
    },
    "required": [],
    "additionalProperties": False,
}


class TestValidateParamsAgainstSchemaUnionTypes:
    """W3A: oneOf / anyOf union branch matching."""

    def test_anyof_accepts_string(self) -> None:
        BaseMCPCommand.validate_params_against_schema(
            {"flexible": "hello"},
            _UNION_SCHEMA,
            "union_test",
        )

    def test_anyof_accepts_integer(self) -> None:
        BaseMCPCommand.validate_params_against_schema(
            {"flexible": 42},
            _UNION_SCHEMA,
            "union_test",
        )

    def test_anyof_rejects_boolean(self) -> None:
        with pytest.raises(
            ValidationError, match="must match at least one branch of anyOf"
        ) as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"flexible": True},
                _UNION_SCHEMA,
                "union_test",
            )
        assert exc_info.value.field == "flexible"
        assert "anyOf" in exc_info.value.details

    def test_oneof_accepts_string(self) -> None:
        BaseMCPCommand.validate_params_against_schema(
            {"selector": "1:10"},
            _UNION_SCHEMA,
            "union_test",
        )

    def test_oneof_accepts_integer_array(self) -> None:
        BaseMCPCommand.validate_params_against_schema(
            {"selector": [0, 1, 2]},
            _UNION_SCHEMA,
            "union_test",
        )

    def test_oneof_accepts_string_array(self) -> None:
        BaseMCPCommand.validate_params_against_schema(
            {"selector": ["block_a", "block_b"]},
            _UNION_SCHEMA,
            "union_test",
        )

    def test_oneof_rejects_mixed_array(self) -> None:
        with pytest.raises(
            ValidationError, match="must match one branch of oneOf"
        ) as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"selector": ["a", 1]},
                _UNION_SCHEMA,
                "union_test",
            )
        assert exc_info.value.field == "selector"
        assert "oneOf" in exc_info.value.details

    def test_oneof_rejects_boolean(self) -> None:
        with pytest.raises(
            ValidationError, match="must match one branch of oneOf"
        ) as exc_info:
            BaseMCPCommand.validate_params_against_schema(
                {"selector": True},
                _UNION_SCHEMA,
                "union_test",
            )
        assert exc_info.value.field == "selector"
