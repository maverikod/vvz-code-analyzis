"""
MCP command: search_close — close a search session and release buffer files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.exceptions import ValidationError
from ..core.search_session.http_access import HttpAccessContext, resolve_session_layout
from ..core.search_session.manifest import read_manifest, update_manifest_atomic
from ..core.search_session.service_metadata import (
    initialize_service_metadata,
    refresh_last_access,
)
import time
from .base_mcp_command import BaseMCPCommand

SESSION_NOT_FOUND = "SESSION_NOT_FOUND"


class SearchCloseCommand(BaseMCPCommand):
    """Close a search session, release buffer scratch files, and invalidate block_position continuation."""

    name = "search_close"
    version = "1.0.0"
    descr = (
        "Close a paginated search session. Sets manifest status to closed, "
        "releases buffer scratch files. Index and blocks remain until cleaner TTL."
    )
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "SearchSession job_id from search handoff.",
                },
            },
            "required": ["job_id"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return validate params."""
        params = super().validate_params(params)
        if not str(params.get("job_id") or "").strip():
            raise ValidationError(
                "job_id must be non-empty", field="job_id", details={}
            )
        return params

    async def execute(self, **kwargs: Any) -> SuccessResult | ErrorResult:  # type: ignore[override]
        """Execute the command."""
        job_id = str(kwargs.get("job_id") or "").strip()
        ctx = HttpAccessContext(sessions_root=self._get_search_sessions_root())
        layout = resolve_session_layout(ctx, job_id)

        if not layout.root.is_dir():
            return ErrorResult(message=f"Search session not found: {job_id}", code=SESSION_NOT_FOUND)  # type: ignore[arg-type]

        if not layout.manifest_path.is_file():
            return ErrorResult(message=f"Search manifest not found: {job_id}", code=SESSION_NOT_FOUND)  # type: ignore[arg-type]

        def _mutator(m):
            """Return mutator."""
            return replace(m, status="closed")

        update_manifest_atomic(layout, _mutator)

        now = time.time()
        if layout.service_metadata_path.is_file():
            refresh_last_access(layout, now=now)
        else:
            initialize_service_metadata(layout, now=now)

        if layout.buffer_dir.is_dir():
            for f in layout.buffer_dir.iterdir():
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

        return SuccessResult(data={"job_id": job_id, "closed": True})

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return command metadata."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "parameters": {
                "job_id": {
                    "description": "SearchSession job_id.",
                    "type": "string",
                    "required": True,
                },
            },
            "error_cases": {
                "SESSION_NOT_FOUND": {"description": "job_id not found."},
            },
            "best_practices": [
                "block_position continuation is invalid after close; search_get_page returns CLOSED_SESSION.",
                "Blocks and index remain readable until background cleaner TTL.",
            ],
        }
