"""
MCP command: search_cancel — cancel a running paginated search session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.exceptions import ValidationError
from ..core.search_session.http_access import HttpAccessContext, resolve_session_layout
from ..core.search_session.manifest import read_manifest, update_manifest_atomic
from ..core.search_session.queue_cancel import (
    cancel_queued_search_job,
    queue_job_id_from_manifest,
)
from ..core.search_session.status import apply_cancellation, snapshot_from_manifest
from .base_mcp_command import BaseMCPCommand

SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
_TERMINAL = frozenset({"completed", "failed", "cancelled", "timed_out", "closed"})


class SearchCancelCommand(BaseMCPCommand):
    """Cancel a running paginated search session via job_id."""

    name = "search_cancel"
    version = "1.0.0"
    descr = (
        "Cancel a running search session. Sets manifest status to cancelled. "
        "Does not interrupt an in-process background search task; poll status instead."
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

        manifest = read_manifest(layout)
        if manifest.status in _TERMINAL:
            return SuccessResult(
                data={
                    "job_id": job_id,
                    "cancelled": False,
                    "message": f"Session already in terminal state: {manifest.status}",
                }
            )

        snapshot = snapshot_from_manifest(manifest)
        cancelled_snapshot = apply_cancellation(snapshot, reason="client_cancel")

        def _mutator(m):
            """Return mutator."""
            return replace(m, status=cancelled_snapshot.status)

        update_manifest_atomic(layout, _mutator)

        queue_job_id = queue_job_id_from_manifest(manifest)
        if queue_job_id:
            await cancel_queued_search_job(queue_job_id)

        return SuccessResult(data={"job_id": job_id, "cancelled": True})

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
                "Repeated cancel returns cancelled=false; idempotent.",
            ],
        }
