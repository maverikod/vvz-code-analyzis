"""
Universal file edit-session workflow on top of :class:`CodeAnalysisAsyncClient`.

Wraps ``universal_file_open`` / ``edit`` / ``write`` / ``close`` / ``preview`` only.
Legacy ``universal_file_read`` / ``universal_file_save`` and CST commands are not
part of this API (see :mod:`server_api`).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from code_analysis_client.responses import unwrap_command_result

if TYPE_CHECKING:
    from code_analysis_client.client import CodeAnalysisAsyncClient


class UniversalFileClient:
    """Edit-session workflow for project files (open → edit → write → close)."""

    __slots__ = ("_client",)

    def __init__(self, client: CodeAnalysisAsyncClient) -> None:
        self._client = client

    async def open(
        self,
        project_id: str,
        file_path: str,
        *,
        create: bool = False,
        initial_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start an edit session (``universal_file_open``)."""
        params: Dict[str, Any] = {
            "project_id": project_id,
            "file_path": file_path,
            "create": create,
        }
        if initial_content is not None:
            params["initial_content"] = initial_content
        return unwrap_command_result(
            await self._client.call_validated("universal_file_open", params)
        )

    async def edit(
        self,
        project_id: str,
        session_id: str,
        operations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Apply draft mutations (``universal_file_edit``)."""
        return unwrap_command_result(
            await self._client.call_validated(
                "universal_file_edit",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "operations": operations,
                },
            )
        )

    async def write(
        self,
        project_id: str,
        session_id: str,
        *,
        write_mode: str = "commit",
    ) -> Dict[str, Any]:
        """Persist or preview draft (``universal_file_write``)."""
        return unwrap_command_result(
            await self._client.call_validated(
                "universal_file_write",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                    "write_mode": write_mode,
                },
            )
        )

    async def close(
        self,
        project_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """End edit session (``universal_file_close``)."""
        return unwrap_command_result(
            await self._client.call_validated(
                "universal_file_close",
                {
                    "project_id": project_id,
                    "session_id": session_id,
                },
            )
        )

    async def preview(
        self,
        project_id: str,
        file_path: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Structured read-only preview (``universal_file_preview``)."""
        params: Dict[str, Any] = {
            "project_id": project_id,
            "file_path": file_path,
        }
        params.update(kwargs)
        return unwrap_command_result(
            await self._client.call_validated("universal_file_preview", params)
        )
