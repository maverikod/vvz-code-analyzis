"""
MCP command: search_get_page — fetch a paginated result block by job_id and block_position.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.exceptions import ValidationError
from ..core.search_session.http_access import HttpAccessContext, resolve_session_layout
from ..core.search_session.manifest import read_manifest
from ..core.search_session.result_index import COMPLETENESS_RUNNING, read_index
from ..core.search_session.service_metadata import (
    initialize_service_metadata,
    refresh_last_access,
)
from ..core.search_session.status import snapshot_from_manifest
from .base_mcp_command import BaseMCPCommand

BLOCK_NOT_READY = "BLOCK_NOT_READY"
SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
CLOSED_SESSION = "CLOSED_SESSION"
_TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "timed_out", "closed"}
)


class SearchGetPageCommand(BaseMCPCommand):
    """Fetch a paginated search result block by job_id and block_position."""

    name = "search_get_page"
    version = "1.0.0"
    descr = (
        "Return one published SearchResultBlock for a paginated search session. "
        "Use job_id from search_start handoff and block_position (1-based)."
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
                    "description": "SearchSession search_id from search_start handoff.",
                },
                "block_position": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1,
                    "description": "1-based block position from job index.",
                },
                "wait_for_new_results": {
                    "type": "boolean",
                    "default": False,
                    "description": "Poll until block available or timeout.",
                },
                "wait_timeout_seconds": {
                    "type": "number",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 30,
                    "description": "Seconds to wait when wait_for_new_results is true.",
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
        pos = params.get("block_position", 1)
        if pos is not None and int(pos) < 1:
            raise ValidationError(
                "block_position must be >= 1", field="block_position", details={}
            )
        return params

    async def execute(
        self,
        job_id: str,
        block_position: int = 1,
        wait_for_new_results: bool = False,
        wait_timeout_seconds: float = 0,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        job_id = str(job_id).strip()
        pos = max(1, int(block_position))
        storage = self._get_shared_storage()
        ctx = HttpAccessContext(config_dir=storage.config_dir)
        layout = resolve_session_layout(ctx, job_id)

        if not layout.root.is_dir():
            return ErrorResult(
                message=f"Search session not found: {job_id}",
                code=SESSION_NOT_FOUND,
            )

        if layout.manifest_path.is_file():
            manifest = read_manifest(layout)
            if manifest.status == "closed":
                return ErrorResult(
                    message=f"Session {job_id} is closed; block_position continuation is invalid.",
                    code=CLOSED_SESSION,
                )

        deadline = (
            time.monotonic() + float(wait_timeout_seconds)
            if wait_for_new_results
            else None
        )

        while True:
            block_path = layout.blocks_dir / f"block_{pos}.json"
            if block_path.is_file():
                with open(block_path, encoding="utf-8") as fh:
                    block_data = json.load(fh)
                self._refresh(layout)
                manifest = (
                    read_manifest(layout) if layout.manifest_path.is_file() else None
                )
                index = (
                    read_index(layout.index_path)
                    if layout.index_path.is_file()
                    else None
                )
                has_more = False
                if index:
                    max_pos = max(
                        (e.get("position", 0) for e in index.blocks), default=0
                    )
                    has_more = (
                        index.completeness == COMPLETENESS_RUNNING or pos < max_pos
                    )
                return SuccessResult(
                    data={
                        "job_id": job_id,
                        "block_position": pos,
                        "items": (
                            block_data.get("items", block_data)
                            if isinstance(block_data, dict)
                            else block_data
                        ),
                        "has_more": has_more,
                        "status": manifest.status if manifest else "unknown",
                        "progress": dict(manifest.metrics) if manifest else {},
                        "warnings": [],
                        "errors": [],
                    }
                )

            if deadline is not None and time.monotonic() < deadline:
                time.sleep(0.25)
                continue

            return ErrorResult(
                message=f"Block {pos} not yet published for job {job_id}.",
                code=BLOCK_NOT_READY,
            )

    def _refresh(self, layout):
        now = time.time()
        if layout.service_metadata_path.is_file():
            refresh_last_access(layout, now=now)
        else:
            initialize_service_metadata(layout, now=now)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "parameters": {
                "job_id": {
                    "description": "SearchSession job_id from search_start.",
                    "type": "string",
                    "required": True,
                },
                "block_position": {
                    "description": "1-based block position.",
                    "type": "integer",
                    "required": False,
                    "default": 1,
                },
                "wait_for_new_results": {
                    "description": "Poll for block.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "wait_timeout_seconds": {
                    "description": "Poll timeout.",
                    "type": "number",
                    "required": False,
                    "default": 0,
                },
            },
            "error_cases": {
                "SESSION_NOT_FOUND": {"description": "job_id not found."},
                "BLOCK_NOT_READY": {"description": "Block not yet published."},
                "CLOSED_SESSION": {
                    "description": "Session closed; continuation invalid."
                },
            },
            "best_practices": [
                "Use block_position from search_start handoff first_block_position.",
                "Increment block_position for subsequent pages; do not use opaque cursor.",
            ],
        }
