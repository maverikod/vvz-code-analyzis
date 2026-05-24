"""
MCP commands: get_entity_dependencies, get_entity_dependents.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional, Union

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.exceptions import ValidationError
from ..base_mcp_command import BaseMCPCommand

from .entity_dependencies_helpers import (
    CALLEE_TYPES,
    CALLER_TYPES,
    get_entity_dependencies_via_execute,
    get_entity_dependents_via_execute,
    resolve_entity_id_by_name,
)
from .entity_dependencies_metadata import (
    get_entity_dependencies_metadata,
    get_entity_dependents_metadata,
)


def _entity_identifier_present(
    entity_id: Optional[Any], entity_name: Optional[Any]
) -> tuple[bool, bool]:
    """Return (has_entity_id, has_entity_name) for non-blank identifier values."""
    has_id = False
    if entity_id is not None:
        if isinstance(entity_id, bool):
            has_id = False
        elif isinstance(entity_id, int):
            has_id = True
        elif isinstance(entity_id, str):
            has_id = bool(entity_id.strip())
    has_name = isinstance(entity_name, str) and bool(entity_name.strip())
    return has_id, has_name


def _validate_entity_id_param(
    raw: Optional[Any], *, command_name: str, field: str = "entity_id"
) -> None:
    """Enforce entity_id anyOf string|integer; reject bool, list, dict, and other types."""
    if raw is None:
        return
    if isinstance(raw, bool):
        raise ValidationError(
            f"{command_name}: parameter {field!r} must be string or integer, got bool",
            field=field,
            details={},
        )
    if isinstance(raw, int):
        return
    if isinstance(raw, str):
        if not raw.strip():
            raise ValidationError(
                f"{command_name}: parameter {field!r} must be a non-empty string",
                field=field,
                details={},
            )
        return
    raise ValidationError(
        f"{command_name}: parameter {field!r} must be string or integer, "
        f"got {type(raw).__name__}",
        field=field,
        details={},
    )


def _validate_entity_identifier_params(
    params: Dict[str, Any], *, command_name: str
) -> None:
    """Require at least one of entity_id or entity_name after schema validation."""
    entity_id = params.get("entity_id")
    entity_name = params.get("entity_name")
    has_id, has_name = _entity_identifier_present(entity_id, entity_name)
    if not has_id and not has_name:
        raise ValidationError(
            f"{command_name}: provide entity_id or entity_name",
            field="entity_id",
            details={},
        )


def _normalize_entity_id_param(
    raw: Optional[Any], *, command_name: str = "command"
) -> Optional[Union[str, int]]:
    """Normalize validated entity_id: strip strings; reject invalid types."""
    if raw is None:
        return None
    _validate_entity_id_param(raw, command_name=command_name)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        return raw.strip()
    return None


class GetEntityDependenciesMCPCommand(BaseMCPCommand):
    """Get dependencies of an entity (what it calls/uses) by entity id."""

    name = "get_entity_dependencies"
    version = "1.0.0"
    descr = (
        "Get list of entities that the given entity depends on (by entity type and id)"
    )
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "entity_type": {
                    "type": "string",
                    "description": (
                        "Type of the entity: 'class', 'method', or 'function'. "
                        "Required when using entity_name."
                    ),
                    "enum": list(CALLER_TYPES),
                },
                "entity_id": {
                    "description": (
                        "Primary key of the entity in classes/functions/methods tables. "
                        "Use a canonical UUID string after DB UUID migration; integer is accepted "
                        "only for pre-migration tooling. Either entity_id or entity_name must be set."
                    ),
                    "anyOf": [
                        {
                            "type": "string",
                            "description": "UUID string (recommended).",
                        },
                        {
                            "type": "integer",
                            "description": "Legacy integer row id (deprecated).",
                        },
                    ],
                },
                "entity_name": {
                    "type": "string",
                    "description": (
                        "Name of the entity. Resolved to id within the project. "
                        "For methods, optionally set target_class."
                    ),
                },
                "target_class": {
                    "type": "string",
                    "description": (
                        "Optional class name when entity_type is 'method' and entity_name is used."
                    ),
                },
            },
            "required": ["project_id", "entity_type"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Enforce entity_id anyOf string|integer and require entity_id or entity_name."""
        params = super().validate_params(params)
        _validate_entity_id_param(params.get("entity_id"), command_name=self.name)
        _validate_entity_identifier_params(params, command_name=self.name)
        return params

    async def execute(
        self,
        project_id: str,
        entity_type: str,
        entity_id: Optional[Any] = None,
        entity_name: Optional[str] = None,
        target_class: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            self._resolve_project_root(project_id)
            db = self._open_database()
            if entity_type not in CALLER_TYPES:
                return ErrorResult(
                    message=f"entity_type must be one of {CALLER_TYPES!r}",
                    code="VALIDATION_ERROR",
                )
            eid = _normalize_entity_id_param(entity_id, command_name=self.name)
            if eid is None:
                if not entity_name:
                    return ErrorResult(
                        message="Provide entity_id or entity_name",
                        code="VALIDATION_ERROR",
                    )
                eid = resolve_entity_id_by_name(
                    db, project_id, entity_type, entity_name, target_class
                )
                if eid is None:
                    return ErrorResult(
                        message=f"Entity not found: {entity_type!r} {entity_name!r}",
                        code="ENTITY_NOT_FOUND",
                    )
            deps = get_entity_dependencies_via_execute(db, entity_type, eid)
            return SuccessResult(data={"dependencies": deps})
        except Exception as e:
            return self._handle_error(
                e, "GET_ENTITY_DEPENDENCIES_ERROR", "get_entity_dependencies"
            )

    @classmethod
    def metadata(cls: type["GetEntityDependenciesMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_entity_dependencies_metadata()


class GetEntityDependentsMCPCommand(BaseMCPCommand):
    """Get dependents of an entity (what calls/uses it) by entity id."""

    name = "get_entity_dependents"
    version = "1.0.0"
    descr = (
        "Get list of entities that depend on the given entity (by entity type and id)"
    )
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "entity_type": {
                    "type": "string",
                    "description": (
                        "Type of the entity: 'class', 'method', or 'function'. "
                        "Required when using entity_name."
                    ),
                    "enum": list(CALLEE_TYPES),
                },
                "entity_id": {
                    "description": (
                        "Primary key of the entity in classes/functions/methods tables. "
                        "Use a canonical UUID string after DB UUID migration; integer is accepted "
                        "only for pre-migration tooling. Either entity_id or entity_name must be set."
                    ),
                    "anyOf": [
                        {
                            "type": "string",
                            "description": "UUID string (recommended).",
                        },
                        {
                            "type": "integer",
                            "description": "Legacy integer row id (deprecated).",
                        },
                    ],
                },
                "entity_name": {
                    "type": "string",
                    "description": (
                        "Name of the entity. Resolved to id within the project. "
                        "For methods, optionally set target_class."
                    ),
                },
                "target_class": {
                    "type": "string",
                    "description": (
                        "Optional class name when entity_type is 'method' and entity_name is used."
                    ),
                },
            },
            "required": ["project_id", "entity_type"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Enforce entity_id anyOf string|integer and require entity_id or entity_name."""
        params = super().validate_params(params)
        _validate_entity_id_param(params.get("entity_id"), command_name=self.name)
        _validate_entity_identifier_params(params, command_name=self.name)
        return params

    async def execute(
        self,
        project_id: str,
        entity_type: str,
        entity_id: Optional[Any] = None,
        entity_name: Optional[str] = None,
        target_class: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            self._resolve_project_root(project_id)
            db = self._open_database()
            if entity_type not in CALLEE_TYPES:
                return ErrorResult(
                    message=f"entity_type must be one of {CALLEE_TYPES!r}",
                    code="VALIDATION_ERROR",
                )
            eid = _normalize_entity_id_param(entity_id, command_name=self.name)
            if eid is None:
                if not entity_name:
                    return ErrorResult(
                        message="Provide entity_id or entity_name",
                        code="VALIDATION_ERROR",
                    )
                eid = resolve_entity_id_by_name(
                    db, project_id, entity_type, entity_name, target_class
                )
                if eid is None:
                    return ErrorResult(
                        message=f"Entity not found: {entity_type!r} {entity_name!r}",
                        code="ENTITY_NOT_FOUND",
                    )
            deps = get_entity_dependents_via_execute(db, entity_type, eid)
            return SuccessResult(data={"dependents": deps})
        except Exception as e:
            return self._handle_error(
                e, "GET_ENTITY_DEPENDENTS_ERROR", "get_entity_dependents"
            )

    @classmethod
    def metadata(cls: type["GetEntityDependentsMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_entity_dependents_metadata()
