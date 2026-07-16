"""
Read-only structured file preview on top of :class:`CodeAnalysisAsyncClient`.

Wraps ``universal_file_preview`` only. Content editing (open/edit/write/close
sessions) is not served by this project's code-analysis server; that workflow
lives in the ai-editor client instead.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from code_analysis_client.responses import unwrap_command_result

if TYPE_CHECKING:
    from code_analysis_client.client import CodeAnalysisAsyncClient


class UniversalFileClient:
    """Read-only structured preview for project files.

    Wraps ``universal_file_preview`` (the only ``universal_file_*`` command
    still registered on the code-analysis server). Content editing belongs to
    the ai-editor client, not this package.
    """

    __slots__ = ("_client",)

    def __init__(self, client: CodeAnalysisAsyncClient) -> None:
        """Store the async client used for universal file preview commands."""
        self._client = client

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
