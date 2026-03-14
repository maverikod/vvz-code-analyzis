"""
MCP commands: get_entity_dependencies, get_entity_dependents.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

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
                    "type": "integer",
                    "description": (
                        "Database ID of the entity. Either entity_id or entity_name must be set."
                    ),
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

    async def execute(
        self,
        project_id: str,
        entity_type: str,
        entity_id: Optional[int] = None,
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
            eid = entity_id
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
                    "type": "integer",
                    "description": (
                        "Database ID of the entity. Either entity_id or entity_name must be set."
                    ),
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

    async def execute(
        self,
        project_id: str,
        entity_type: str,
        entity_id: Optional[int] = None,
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
            eid = entity_id
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
