"""
MCP command: search_get_status — return session status without result payloads.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.exceptions import ValidationError
from ..core.search_session.http_access import HttpAccessContext, resolve_session_layout
from ..core.search_session.manifest import read_manifest
from ..core.search_session.service_metadata import (
    initialize_service_metadata,
    refresh_last_access,
)
from ..core.search_session.status import snapshot_from_manifest
from .base_mcp_command import BaseMCPCommand

SESSION_NOT_FOUND = "SESSION_NOT_FOUND"


class SearchGetStatusCommand(BaseMCPCommand):
    """Return search session status and metrics without result row payloads."""

    name = "search_get_status"
    version = "1.0.0"
    descr = (
        "Return SearchSession status, phase, and progress metrics without result rows. "
        "Distinct from HTTP GET /status route (HTTPResultAccess)."
    )
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "SearchSession job_id from search_start handoff.",
                },
            },
            "required": ["job_id"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        if not str(params.get("job_id") or "").strip():
            raise ValidationError(
                "job_id must be non-empty", field="job_id", details={}
            )
        return params

    async def execute(self, job_id: str, **kwargs: Any) -> SuccessResult | ErrorResult:
        job_id = str(job_id).strip()
        storage = self._get_shared_storage()
        ctx = HttpAccessContext(config_dir=storage.config_dir)
        layout = resolve_session_layout(ctx, job_id)

        if not layout.root.is_dir():
            return ErrorResult(
                message=f"Search session not found: {job_id}", code=SESSION_NOT_FOUND
            )

        if not layout.manifest_path.is_file():
            return ErrorResult(
                message=f"Search manifest not found: {job_id}", code=SESSION_NOT_FOUND
            )

        manifest = read_manifest(layout)
        snapshot = snapshot_from_manifest(manifest)

        now = time.time()
        if layout.service_metadata_path.is_file():
            refresh_last_access(layout, now=now)
        else:
            initialize_service_metadata(layout, now=now)

        return SuccessResult(
            data={
                "job_id": job_id,
                "status": snapshot.status,
                "phase": snapshot.phase.value,
                "block_not_ready": snapshot.block_not_ready,
                "message": snapshot.message,
                "progress": dict(manifest.metrics),
                "block_ready_count": manifest.block_ready_count,
                "summary": {
                    "produced_results": manifest.metrics.get("produced_results", 0),
                    "written_blocks": manifest.metrics.get("written_blocks", 0),
                },
                "warnings": [],
                "errors": [],
            }
        )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "Returns status and progress without result rows. "
                "Use search_get_page to read block items. "
                "Distinct from HTTPResultAccess GET /jobs/{job_id}/status."
            ),
            "parameters": {
                "job_id": {
                    "description": "SearchSession job_id.",
                    "type": "string",
                    "required": True,
                },
            },
            "error_cases": {
                "SESSION_NOT_FOUND": {
                    "description": "job_id not found or manifest missing."
                },
            },
        }
