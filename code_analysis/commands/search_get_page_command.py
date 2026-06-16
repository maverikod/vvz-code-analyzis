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
from ..core.search_session.page_payload import temporal_page_payload
from ..core.search_session.result_block import block_items_from_payload
from ..core.search_session.result_index import COMPLETENESS_RUNNING, read_index
from ..core.search_session.search_profile_log import open_search_profile_recorder
from ..core.search_session.service_metadata import (
    initialize_service_metadata,
    refresh_last_access,
)
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
        "Use job_id from search handoff and block_position (1-based)."
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
                    "description": "SearchSession job_id from search handoff.",
                },
                "block_position": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1,
                    "description": "1-based block position from job index.",
                },
                "ordering": {
                    "type": "string",
                    "enum": ["temporal", "relevance"],
                    "default": "temporal",
                    "description": "Block set to read: temporal (arrival order) or relevance (score DESC).",
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

    async def execute(self, **kwargs: Any) -> SuccessResult | ErrorResult:  # type: ignore[override]
        try:
            params = self.validate_params(
                {k: v for k, v in kwargs.items() if k != "context"}
            )
        except ValidationError as exc:
            return self._handle_error(exc, "VALIDATION_ERROR", self.name)

        job_id = str(params["job_id"]).strip()
        pos = max(1, int(params.get("block_position") or 1))
        ordering = str(params.get("ordering") or "temporal")
        wait = bool(params.get("wait_for_new_results", False))
        timeout = float(params.get("wait_timeout_seconds") or 0)
        profile = open_search_profile_recorder(
            job_id=job_id,
            raw_config=self._get_raw_config(),
            config_path=self._resolve_config_path(),
        )
        profile.checkpoint(
            "get_page_start",
            block_position=pos,
            ordering=ordering,
            wait=wait,
        )
        ctx = HttpAccessContext(sessions_root=self._get_search_sessions_root())
        layout = resolve_session_layout(ctx, job_id)

        if not layout.root.is_dir():
            profile.checkpoint("get_page_error", code=SESSION_NOT_FOUND)
            return ErrorResult(
                message=f"Search session not found: {job_id}",
                code=SESSION_NOT_FOUND,  # type: ignore[arg-type]
            )

        if layout.manifest_path.is_file():
            manifest = read_manifest(layout)
            if manifest.status == "closed":
                return ErrorResult(
                    message=f"Session {job_id} is closed; block_position continuation is invalid.",
                    code=CLOSED_SESSION,  # type: ignore[arg-type]
                )

        # Choose block directory based on ordering.
        if ordering == "relevance":
            blocks_dir = layout.relevance_blocks_dir
        else:
            blocks_dir = layout.blocks_dir

        deadline = time.monotonic() + timeout if wait else None

        while True:
            block_path = blocks_dir / f"block_{pos}.json"
            if block_path.is_file():
                self._refresh(layout)
                if ordering == "relevance":
                    with open(block_path, encoding="utf-8") as fh:
                        block_data = json.load(fh)
                    manifest_obj = (
                        read_manifest(layout)
                        if layout.manifest_path.is_file()
                        else None
                    )
                    index = (
                        read_index(layout.index_path)
                        if layout.index_path.is_file()
                        else None
                    )
                    has_more = False
                    if index:
                        max_pos = max(
                            (e.get("position", 0) for e in index.relevance_blocks),
                            default=0,
                        )
                        has_more = pos < max_pos
                    items = block_items_from_payload(block_data)
                    profile.checkpoint(
                        "get_page_done",
                        items=len(items),
                        has_more=has_more,
                    )
                    return SuccessResult(
                        data={
                            "job_id": job_id,
                            "block_position": pos,
                            "ordering": ordering,
                            "items": items,
                            "has_more": has_more,
                            "status": (
                                manifest_obj.status if manifest_obj else "unknown"
                            ),
                            "progress": (
                                dict(manifest_obj.metrics) if manifest_obj else {}
                            ),
                            "warnings": [],
                            "errors": [],
                        }
                    )
                page_data = temporal_page_payload(
                    layout=layout,
                    job_id=job_id,
                    block_position=pos,
                    search_still_running=False,
                )
                profile.checkpoint(
                    "get_page_done",
                    items=len(page_data.get("items") or []),
                    has_more=page_data.get("has_more"),
                )
                return SuccessResult(data=page_data)

            if deadline is not None and time.monotonic() < deadline:
                time.sleep(0.25)
                continue

            profile.checkpoint("get_page_error", code=BLOCK_NOT_READY)
            return ErrorResult(
                message=f"Block {pos} not yet published for job {job_id} (ordering={ordering}).",
                code=BLOCK_NOT_READY,  # type: ignore[arg-type]
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
                    "description": "SearchSession job_id from search handoff.",
                    "type": "string",
                    "required": True,
                },
                "block_position": {
                    "description": "1-based block position.",
                    "type": "integer",
                    "required": False,
                    "default": 1,
                },
                "ordering": {
                    "description": "temporal (live) or relevance (after completed).",
                    "type": "string",
                    "required": False,
                    "default": "temporal",
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
            "return_value": {
                "success": {
                    "description": "One result block.",
                    "data": {
                        "job_id": "Session id",
                        "block_position": "Requested block index",
                        "ordering": "temporal or relevance",
                        "items": "Finding rows for this block",
                        "has_more": "True when more blocks may arrive or exist",
                        "status": "Session manifest status",
                        "progress": "Manifest metrics dict",
                    },
                },
            },
            "error_cases": {
                "SESSION_NOT_FOUND": {"description": "job_id not found."},
                "BLOCK_NOT_READY": {"description": "Block not yet published."},
                "CLOSED_SESSION": {
                    "description": "Session closed; continuation invalid."
                },
                "VALIDATION_ERROR": {
                    "description": "Invalid job_id or block_position."
                },
            },
            "best_practices": [
                "Use first_block_position from search handoff for the first page.",
                "Increment block_position for subsequent pages; do not use opaque cursor.",
                "Use ordering=relevance after search_get_status reports completed.",
            ],
        }
