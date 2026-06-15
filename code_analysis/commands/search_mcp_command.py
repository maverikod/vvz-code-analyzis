"""
MCP command: search — paginated cross-project search (fulltext + optional semantic/grep).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
import uuid
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.exceptions import ValidationError
from ..core.search_session.compatibility import (
    PaginatedSearchHandoff,
    handoff_to_response,
)
from ..core.search_session.directory import (
    SearchSessionDirectoryLayout,
    provision_search_session_directory,
)
from ..core.search_session.session import SearchSession, SearchSessionState
from .base_mcp_command import BaseMCPCommand
from .project_cross_search_command import ProjectCrossSearchCommand
from .search_paginated_cross import run_paginated_cross

logger = logging.getLogger(__name__)

_FIRST_BLOCK_WAIT_SECONDS = 30.0


class SearchMCPCommand(BaseMCPCommand):
    """
    Start paginated cross search: fulltext always on; semantic and grep optional.

    Returns a job handoff as soon as the first result block is published (or the
    indexed phase finishes). Remaining work continues in the background; use
    ``search_get_status`` and ``search_get_page`` to poll and paginate.
    """

    name = "search"
    version = "1.0.0"
    descr = (
        "Cross search with incremental paginated results. Fulltext always runs; "
        "set enable_semantic or enable_grep to opt in. Returns job_id immediately "
        "after first hits; use search_get_page and search_get_status to continue."
    )
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_id", "query"],
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query text.",
                },
                "enable_semantic": {
                    "type": "boolean",
                    "default": True,
                    "description": "When false, skip semantic (vector) search.",
                },
                "enable_grep": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, grep index-gap files on disk after indexed phase.",
                },
                "grep_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Grep patterns; defaults to [query] when enable_grep is true.",
                },
                "fulltext_limit": {
                    "type": "integer",
                    "default": 30,
                    "minimum": 1,
                    "maximum": 200,
                    "description": "Max fulltext (BM25) hits to fetch.",
                },
                "semantic_limit": {
                    "type": "integer",
                    "default": 30,
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Max semantic hits when enable_semantic is true.",
                },
                "page_size": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 200,
                    "description": (
                        "Maximum findings per published block (also bounded by "
                        "server search_session.max_block_size_bytes)."
                    ),
                },
                "min_semantic_score": {
                    "type": "number",
                    "default": 0.45,
                    "description": "Minimum vector similarity score for semantic hits.",
                },
                "require_structural_grep": {
                    "type": "boolean",
                    "default": True,
                    "description": "When enable_grep, prefer structural node_ref evidence.",
                },
                "literal": {
                    "type": "boolean",
                    "default": True,
                    "description": "Grep literal (non-regex) mode when enable_grep.",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "default": False,
                    "description": "Grep case sensitivity when enable_grep.",
                },
                "hard_timeout_seconds": {
                    "type": "number",
                    "default": 120.0,
                    "description": "Wall-clock cap for grep phase.",
                },
                "first_block_wait_seconds": {
                    "type": "number",
                    "default": _FIRST_BLOCK_WAIT_SECONDS,
                    "minimum": 0,
                    "maximum": 120,
                    "description": "Max seconds to wait for block_1 before returning handoff.",
                },
            },
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        query = str(params.get("query") or "").strip()
        if not query:
            raise ValidationError("query must be non-empty", field="query", details={})
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        params["enable_semantic"] = bool(params.get("enable_semantic", True))
        params["enable_grep"] = bool(params.get("enable_grep", False))
        return params

    async def execute(self, **kwargs: Any) -> SuccessResult | ErrorResult:
        try:
            params = self.validate_params(
                {k: v for k, v in kwargs.items() if k != "context"}
            )
        except ValidationError as exc:
            return self._handle_error(exc, "VALIDATION_ERROR", self.name)

        sessions_root = self._get_search_sessions_root()
        sessions_root.mkdir(parents=True, exist_ok=True)
        search_id = str(uuid.uuid4())
        layout = provision_search_session_directory(
            sessions_root=sessions_root,
            search_id=search_id,
        )
        session = SearchSession(
            search_id=search_id,
            state=SearchSessionState.running,
            directory_path=layout.root,
        )
        wait_seconds = float(
            params.get("first_block_wait_seconds", _FIRST_BLOCK_WAIT_SECONDS)
        )

        async def _background() -> None:
            try:
                await run_paginated_cross(
                    command=ProjectCrossSearchCommand(),
                    params=params,
                    session=session,
                    layout=layout,
                    raw_config=self._get_raw_config(),
                )
            except Exception:
                logger.exception("search background job failed: %s", search_id)
                shutil.rmtree(layout.root, ignore_errors=True)

        task = asyncio.create_task(_background(), name=f"search-{search_id[:8]}")
        first_block_position = await self._wait_for_first_block(
            layout=layout,
            task=task,
            timeout_seconds=wait_seconds,
        )
        search_still_running = not task.done()
        handoff = PaginatedSearchHandoff(
            job_id=search_id,
            index_url=f"/search/jobs/{search_id}/index",
            first_block_position=first_block_position,
            legacy_payload=None,
        )
        payload = handoff_to_response(handoff)
        payload["search_still_running"] = search_still_running
        payload["status"] = "running" if search_still_running else "completed"
        return SuccessResult(data=payload)

    @staticmethod
    async def _wait_for_first_block(
        *,
        layout: SearchSessionDirectoryLayout,
        task: asyncio.Task[None],
        timeout_seconds: float,
    ) -> Optional[int]:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        block_path = layout.blocks_dir / "block_1.json"
        while True:
            if block_path.is_file():
                return 1
            if task.done():
                return None
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(0.05)

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
                "Unified paginated cross search. Fulltext (BM25) always runs first and "
                "results stream into blocks under the service state directory. Optional "
                "semantic and grep phases run afterward; ``search_still_running`` in the "
                "handoff indicates background work. After completion, relevance-sorted "
                "blocks are available via search_get_page with ordering=relevance."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID.",
                    "type": "string",
                    "required": True,
                },
                "query": {
                    "description": "Search text.",
                    "type": "string",
                    "required": True,
                },
                "enable_semantic": {
                    "description": "Include vector semantic search.",
                    "type": "boolean",
                    "default": True,
                },
                "enable_grep": {
                    "description": "Grep unindexed files on disk.",
                    "type": "boolean",
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Fulltext-only quick search",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "query": "load_raw_config",
                        "enable_semantic": False,
                        "enable_grep": False,
                    },
                    "explanation": "BM25 only; first block returned as soon as hits are indexed.",
                },
                {
                    "description": "Full cross search with pagination",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "query": "watch directory",
                        "enable_semantic": True,
                        "enable_grep": True,
                    },
                    "explanation": "Then poll search_get_status and search_get_page by job_id.",
                },
            ],
            "error_cases": {
                "VALIDATION_ERROR": {
                    "description": "Missing or invalid parameters.",
                    "message": "Validation failed",
                    "solution": "Provide project_id and non-empty query.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Paginated search handoff.",
                    "data": {
                        "success": "True",
                        "paginated": "True",
                        "job_id": "Session UUID for search_get_page / search_get_status",
                        "index_url": "HTTP path /search/jobs/{job_id}/index",
                        "first_block_position": "1 when block_1 exists, else null",
                        "search_still_running": "True while background phases continue",
                        "status": "running or completed at handoff time",
                    },
                },
                "error": {
                    "description": "Validation failure.",
                    "code": "VALIDATION_ERROR",
                },
            },
            "best_practices": [
                "Call search_get_status(job_id) to see phase and block_ready_count.",
                "Use search_get_page with wait_for_new_results=true for the next block.",
                "Use ordering=relevance after status is completed for score-sorted pages.",
            ],
        }
