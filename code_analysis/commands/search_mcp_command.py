"""
MCP command: search — paginated cross-project search (fulltext + optional semantic/grep).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import threading
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
from ..core.search_session.page_payload import temporal_page_payload
from ..core.search_session.search_profile_log import (
    open_search_profile_recorder,
    request_summary_fields,
)
from ..core.search_session.session import SearchSession, SearchSessionState
from .base_mcp_command import BaseMCPCommand
from .command_metadata_helpers import build_command_metadata
from .search_paginated_cross import run_paginated_cross

logger = logging.getLogger(__name__)

_FIRST_BLOCK_WAIT_SECONDS = 30.0


def _run_paginated_cross_in_thread(
    *,
    params: Dict[str, Any],
    session: SearchSession,
    layout: SearchSessionDirectoryLayout,
    raw_config: Dict[str, Any],
    search_id: str,
) -> None:
    """Run the full paginated search in a dedicated thread + event loop."""

    async def _runner() -> None:
        """Return runner."""
        try:
            await run_paginated_cross(
                # BaseMCPCommand-typed support instance (retyped off the deleted
                # ProjectCrossSearchCommand): run_paginated_cross only ever calls
                # its BaseMCPCommand-inherited _resolve_project_root /
                # _open_database_from_config, so any concrete BaseMCPCommand
                # works here - reuse SearchMCPCommand itself rather than adding
                # a new throwaway class.
                command=SearchMCPCommand(),
                params=params,
                session=session,
                layout=layout,
                raw_config=raw_config,
            )
        except Exception:
            logger.exception("search background job failed: %s", search_id)
            shutil.rmtree(layout.root, ignore_errors=True)

    try:
        asyncio.run(_runner())
    except Exception:
        logger.exception("search background thread failed: %s", search_id)
        shutil.rmtree(layout.root, ignore_errors=True)


class SearchMCPCommand(BaseMCPCommand):
    """
    Start paginated cross search: fulltext always on; semantic and grep optional.

    Returns the first result page as soon as block_1 is published (or when the
    wait timeout elapses). Remaining work continues in the background; use
    ``search_get_status`` and ``search_get_page`` for later blocks.
    """

    name = "search"
    version = "1.0.0"
    descr = (
        "Cross search with incremental paginated results. Fulltext always runs; "
        "set enable_semantic or enable_grep to opt in. Waits for the first result "
        "block and returns it inline; use search_get_page for subsequent blocks."
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
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "project_id": {
                    "type": ["string", "null"],
                    "description": (
                        "Project UUID. Use list_projects to discover valid values. "
                        "Omit or pass null to search ALL projects (global search): "
                        "fulltext always works globally; semantic works globally only "
                        "on the pgvector backend (FAISS has no cross-project index and "
                        "is skipped with a note); enable_grep=true requires an explicit "
                        "project_id (grep scans one project's files on disk)."
                    ),
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
                "file_pattern": {
                    "type": "string",
                    "default": "",
                    "description": (
                        "Optional project-relative path filter (fnmatch/prefix; same rules as "
                        "list_project_files file_pattern). Narrows fulltext, semantic, and grep."
                    ),
                },
                "path_filter": {
                    "type": "string",
                    "default": "",
                    "description": (
                        "Alias of file_pattern for narrowing search scope. When both are set, "
                        "they must match; file_pattern wins when only one is provided."
                    ),
                },
            },
        }

    @staticmethod
    def _normalize_file_pattern_params(params: Dict[str, Any]) -> None:
        """Return normalize file pattern params."""
        file_pattern = str(params.get("file_pattern") or "").strip()
        path_filter = str(params.get("path_filter") or "").strip()
        if file_pattern and path_filter and file_pattern != path_filter:
            raise ValidationError(
                "file_pattern and path_filter disagree; use one or set the same value",
                field="path_filter",
                details={"file_pattern": file_pattern, "path_filter": path_filter},
            )
        params["file_pattern"] = file_pattern or path_filter

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return validate params."""
        params = super().validate_params(params)
        self._normalize_file_pattern_params(params)
        query = str(params.get("query") or "").strip()
        if not query:
            raise ValidationError("query must be non-empty", field="query", details={})
        project_id = params.get("project_id")
        params["enable_semantic"] = bool(params.get("enable_semantic", True))
        params["enable_grep"] = bool(params.get("enable_grep", False))
        if project_id is None:
            # Global search (project_id=None) = all projects; grep scans one
            # project's files on disk, so it has no meaning here - fail loud
            # instead of silently searching zero/wrong files.
            if params["enable_grep"]:
                raise ValidationError(
                    "grep requires project_id: enable_grep=true is not supported "
                    "with project_id=None (global search); pass an explicit "
                    "project_id or set enable_grep=false",
                    field="project_id",
                    details={"enable_grep": True, "project_id": None},
                )
        else:
            BaseMCPCommand._validate_project_id_exists(project_id)
        return params

    async def execute(self, **kwargs: Any) -> SuccessResult | ErrorResult:
        """Execute the command."""
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
        config_path = self._resolve_config_path()
        raw_config = self._get_raw_config()
        profile = open_search_profile_recorder(
            job_id=search_id,
            raw_config=raw_config,
            config_path=config_path,
        )
        profile.checkpoint(
            "search_execute_start",
            **request_summary_fields(params),
            first_block_wait_seconds=wait_seconds,
        )

        background_thread = threading.Thread(
            target=_run_paginated_cross_in_thread,
            kwargs={
                "params": params,
                "session": session,
                "layout": layout,
                "raw_config": raw_config,
                "search_id": search_id,
            },
            name=f"search-{search_id[:8]}",
            daemon=True,
        )
        background_thread.start()
        profile.checkpoint("search_background_spawned", dedicated_thread=True)
        wait_t0 = time.monotonic()
        first_block_position = await self._wait_for_first_block(
            layout=layout,
            background_thread=background_thread,
            timeout_seconds=wait_seconds,
        )
        search_still_running = background_thread.is_alive()
        profile.checkpoint(
            "search_wait_block1_done",
            block1_found=first_block_position is not None,
            wait_sec=round(time.monotonic() - wait_t0, 4),
            background_done=not search_still_running,
        )
        block_position = first_block_position if first_block_position is not None else 1
        handoff = PaginatedSearchHandoff(
            job_id=search_id,
            index_url=f"/search/jobs/{search_id}/index",
            first_block_position=first_block_position,
            legacy_payload=None,
        )
        payload = handoff_to_response(handoff)
        page = temporal_page_payload(
            layout=layout,
            job_id=search_id,
            block_position=block_position,
            search_still_running=search_still_running,
        )
        payload.update(page)
        payload["search_still_running"] = search_still_running
        payload["notes"] = self._read_session_notes(layout)
        profile.checkpoint(
            "search_execute_return",
            items=len(page.get("items") or []),
            has_more=page.get("has_more"),
            first_block_position=first_block_position,
        )
        return SuccessResult(data=payload)

    @staticmethod
    def _read_session_notes(layout: SearchSessionDirectoryLayout) -> list[str]:
        """Best-effort read of this session's notes.json (written by
        run_paginated_cross, e.g. when a phase is skipped for global search -
        see search_paginated_cross._write_session_note). Empty list when the
        file does not exist yet or the search never needed to write one."""
        notes_path = layout.root / "notes.json"
        if not notes_path.is_file():
            return []
        try:
            data = json.loads(notes_path.read_text())
            notes = data.get("notes")
            return [str(n) for n in notes] if isinstance(notes, list) else []
        except Exception:
            return []

    @staticmethod
    async def _wait_for_first_block(
        *,
        layout: SearchSessionDirectoryLayout,
        background_thread: threading.Thread,
        timeout_seconds: float,
    ) -> Optional[int]:
        """Return wait for first block."""
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        block_path = layout.blocks_dir / "block_1.json"
        while True:
            if block_path.is_file():
                return 1
            if not background_thread.is_alive():
                return None
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(0.05)

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Return command metadata."""
        return build_command_metadata(
            cls,
            detailed_description=(
                "Unified paginated cross search. Fulltext (BM25) always runs first and "
                "results stream into blocks under the service state directory. The command "
                "waits until block_1 exists (or first_block_wait_seconds elapses), then "
                "returns job_id plus the first page (items, has_more). Optional semantic "
                "and grep phases continue in a dedicated background thread (same process) "
                "and publish further blocks incrementally. Use file_pattern or path_filter "
                "to narrow hits to a project-relative subtree."
            ),
            usage_examples=[
                {
                    "description": "Fulltext-only quick search",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "query": "load_raw_config",
                        "enable_semantic": False,
                        "enable_grep": False,
                    },
                    "explanation": "BM25 only; response includes first items when block_1 is ready.",
                },
                {
                    "description": "Search within a subtree",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "query": "validate_params",
                        "path_filter": "code_analysis/commands",
                    },
                    "explanation": "path_filter is an alias of file_pattern.",
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
            error_cases={
                "VALIDATION_ERROR": {
                    "description": "Missing or invalid parameters.",
                    "message": "Validation failed",
                    "solution": "Provide project_id and non-empty query.",
                },
            },
            return_value={
                "success": {
                    "description": "Paginated search handoff with first result page.",
                    "data": {
                        "success": "True",
                        "paginated": "True",
                        "job_id": "Session UUID for search_get_page / search_get_status",
                        "index_url": "HTTP path /search/jobs/{job_id}/index",
                        "first_block_position": "1 when block_1 exists, else null",
                        "block_position": "Same as first page (usually 1)",
                        "ordering": "temporal",
                        "items": "First page of findings (may be empty if timeout before block_1)",
                        "has_more": "True when more blocks may arrive or exist",
                        "search_still_running": "True while background phases continue",
                        "status": "Session manifest status",
                        "progress": "Manifest metrics dict",
                    },
                },
                "error": {
                    "description": "Validation failure.",
                    "code": "VALIDATION_ERROR",
                },
            },
            best_practices=[
                "First response already contains items for block 1 when hits exist.",
                "Call search_get_page(job_id, block_position=2, ...) for the next page.",
                "Call search_get_status(job_id) to see phase and block_ready_count.",
                "Use ordering=relevance after status is completed for score-sorted pages.",
                "Use file_pattern or path_filter to limit fulltext, semantic, and grep phases.",
            ],
        )
