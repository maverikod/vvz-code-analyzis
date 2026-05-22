"""
MCP commands for subordinate client session links (CRUD + list).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.sessions.subordinate_session_commands_metadata import (
    composite_key_schema,
    get_subordinate_session_create_metadata,
    get_subordinate_session_delete_metadata,
    get_subordinate_session_get_metadata,
    get_subordinate_session_list_metadata,
    get_subordinate_session_update_metadata,
)
from code_analysis.core.client_sessions import SessionNotFoundError
from code_analysis.core.subordinate_sessions import (
    SubordinateSessionAlreadyExistsError,
    SubordinateSessionNotFoundError,
    create_subordinate_session,
    delete_subordinate_session,
    get_subordinate_session,
    list_subordinate_sessions,
    update_subordinate_session,
)


def _invalid_params_result(exc: ValueError) -> ErrorResult:
    return ErrorResult(code="INVALID_PARAMS", message=str(exc))


def _default_server_uuid(command: BaseMCPCommand) -> str:
    raw_config = command._get_raw_config()
    return str(raw_config.get("registration", {}).get("instance_uuid", "") or "")


class SubordinateSessionCreateCommand(BaseMCPCommand):
    """Create a subordinate session link."""

    name = "subordinate_session_create"
    version = "1.0.0"
    descr = "Link a subordinate client session to a leading session on a server."
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        schema = composite_key_schema(include_comment=True)
        schema["properties"]["server_uuid"][
            "description"
        ] = "Server instance UUID4. Defaults to registration.instance_uuid when omitted."
        schema["required"] = [
            "parent_session_id",
            "subordinate_session_id",
            "comment",
        ]
        return {
            "type": "object",
            "properties": schema["properties"],
            "required": schema["required"],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        parent_session_id: str,
        subordinate_session_id: str,
        comment: str,
        server_uuid: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        server = server_uuid or _default_server_uuid(self)
        if not server:
            return ErrorResult(
                code="INVALID_PARAMS",
                message="server_uuid is required when registration.instance_uuid is unset.",
            )
        database = self._open_database_from_config()
        try:
            row = create_subordinate_session(
                database,
                parent_session_id=parent_session_id,
                subordinate_session_id=subordinate_session_id,
                server_uuid=server,
                comment=comment,
            )
        except SessionNotFoundError as e:
            return ErrorResult(code="SESSION_NOT_FOUND", message=str(e))
        except SubordinateSessionAlreadyExistsError as e:
            return ErrorResult(
                code="SUBORDINATE_SESSION_ALREADY_EXISTS", message=str(e)
            )
        except ValueError as e:
            return _invalid_params_result(e)
        return SuccessResult(data=row)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_subordinate_session_create_metadata(cls)


class SubordinateSessionGetCommand(BaseMCPCommand):
    """Read one subordinate session link."""

    name = "subordinate_session_get"
    version = "1.0.0"
    descr = "Get one subordinate session link by composite key."
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        schema = composite_key_schema()
        return {
            "type": "object",
            "properties": schema["properties"],
            "required": schema["required"],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        parent_session_id: str,
        subordinate_session_id: str,
        server_uuid: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        database = self._open_database_from_config()
        try:
            row = get_subordinate_session(
                database,
                parent_session_id=parent_session_id,
                subordinate_session_id=subordinate_session_id,
                server_uuid=server_uuid,
            )
        except ValueError as e:
            return _invalid_params_result(e)
        if row is None:
            return ErrorResult(
                code="SUBORDINATE_SESSION_NOT_FOUND",
                message=(
                    "Subordinate session link not found for "
                    f"parent={parent_session_id!r}, "
                    f"subordinate={subordinate_session_id!r}, "
                    f"server={server_uuid!r}."
                ),
            )
        return SuccessResult(data=row)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_subordinate_session_get_metadata(cls)


class SubordinateSessionUpdateCommand(BaseMCPCommand):
    """Update comment on a subordinate session link."""

    name = "subordinate_session_update"
    version = "1.0.0"
    descr = "Update the comment on a subordinate session link."
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        schema = composite_key_schema(include_comment=True)
        return {
            "type": "object",
            "properties": schema["properties"],
            "required": schema["required"],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        parent_session_id: str,
        subordinate_session_id: str,
        server_uuid: str,
        comment: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        database = self._open_database_from_config()
        try:
            row = update_subordinate_session(
                database,
                parent_session_id=parent_session_id,
                subordinate_session_id=subordinate_session_id,
                server_uuid=server_uuid,
                comment=comment,
            )
        except SubordinateSessionNotFoundError as e:
            return ErrorResult(code="SUBORDINATE_SESSION_NOT_FOUND", message=str(e))
        except ValueError as e:
            return _invalid_params_result(e)
        return SuccessResult(data=row)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_subordinate_session_update_metadata(cls)


class SubordinateSessionDeleteCommand(BaseMCPCommand):
    """Delete a subordinate session link."""

    name = "subordinate_session_delete"
    version = "1.0.0"
    descr = "Delete a subordinate session link (not the client sessions themselves)."
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        schema = composite_key_schema()
        return {
            "type": "object",
            "properties": schema["properties"],
            "required": schema["required"],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        parent_session_id: str,
        subordinate_session_id: str,
        server_uuid: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        database = self._open_database_from_config()
        try:
            result = delete_subordinate_session(
                database,
                parent_session_id=parent_session_id,
                subordinate_session_id=subordinate_session_id,
                server_uuid=server_uuid,
            )
        except SubordinateSessionNotFoundError as e:
            return ErrorResult(code="SUBORDINATE_SESSION_NOT_FOUND", message=str(e))
        except ValueError as e:
            return _invalid_params_result(e)
        return SuccessResult(data=result)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_subordinate_session_delete_metadata(cls)


class SubordinateSessionListCommand(BaseMCPCommand):
    """List subordinate session links."""

    name = "subordinate_session_list"
    version = "1.0.0"
    descr = "List subordinate session links with optional filters."
    category = "session_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "parent_session_id": {
                    "type": "string",
                    "description": "Optional filter: leading session UUID4.",
                },
                "subordinate_session_id": {
                    "type": "string",
                    "description": "Optional filter: subordinate session UUID4.",
                },
                "server_uuid": {
                    "type": "string",
                    "description": "Optional filter: server instance UUID4.",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(  # type: ignore[override]
        self,
        parent_session_id: Optional[str] = None,
        subordinate_session_id: Optional[str] = None,
        server_uuid: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        _ = kwargs
        database = self._open_database_from_config()
        try:
            rows = list_subordinate_sessions(
                database,
                parent_session_id=parent_session_id,
                subordinate_session_id=subordinate_session_id,
                server_uuid=server_uuid,
            )
        except ValueError as e:
            return _invalid_params_result(e)
        return SuccessResult(data={"links": rows, "count": len(rows)})

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return get_subordinate_session_list_metadata(cls)
