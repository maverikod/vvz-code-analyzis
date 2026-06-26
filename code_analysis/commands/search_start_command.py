"""
MCP command: search_start

Bridge command for legacy and paginated SearchSession-backed search execution.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from dataclasses import replace
from typing import Any, Callable, Dict, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.exceptions import ValidationError
from ..core.search_session.atomic_publication import atomic_write_json
from ..core.search_session.block_assembler import BlockAssembler
from ..core.search_session.compatibility import (
    BRIDGE_COMMANDS,
    maybe_route_paginated,
)
from ..core.search_session.directory import (
    SearchSessionDirectoryLayout,
    provision_search_session_directory,
)
from ..core.search_session.grep_mode_params import grep_mode_to_fs_ggrep_params
from ..core.search_session.manifest import (
    DEFAULT_METRICS,
    SearchSessionManifest,
    capture_server_process_identity,
    update_manifest_atomic,
    write_manifest_atomic,
)
from ..core.search_session.policy import load_session_ttl_policy
from ..core.search_session.raw_finding_buffer import RawFindingBuffer
from ..core.search_session.result_index import (
    COMPLETENESS_FINISHED,
    append_block_entry,
    mark_index_finished,
)
from ..core.search_session.service_metadata import initialize_service_metadata
from ..core.search_session.session import SearchSession, SearchSessionState
from .base_mcp_command import BaseMCPCommand
from .fs_ggrep_pagination_schema import get_fs_ggrep_schema_with_pagination
from .fs_grep_command import FsGrepCommand
from .fs_grep_structural_integration import GrepSearchMode
from .project_cross_search_command import ProjectCrossSearchCommand
from .project_cross_search_pagination_schema import (
    get_project_cross_search_schema_with_pagination,
)
from .search_mcp_commands_fulltext import FulltextSearchMCPCommand
from .search_session_schema import merge_pagination_schema
from .semantic_search_mcp import SemanticSearchMCPCommand
from .semantic_search_pagination_schema import (
    get_semantic_search_schema_with_pagination,
)

logger = logging.getLogger(__name__)

SEARCH_TYPES = tuple(BRIDGE_COMMANDS["search_start"])

_PAGINATED_SCHEMA_BY_TYPE: dict[str, Callable[[], dict[str, Any]]] = {
    "fulltext": FulltextSearchMCPCommand.get_schema,
    "semantic": get_semantic_search_schema_with_pagination,
    "grep": get_fs_ggrep_schema_with_pagination,
    "cross": get_project_cross_search_schema_with_pagination,
    "tree_query": FulltextSearchMCPCommand.get_schema,
}

_LEGACY_COMMAND_BY_TYPE: dict[str, type[BaseMCPCommand]] = {
    "fulltext": FulltextSearchMCPCommand,
    "semantic": SemanticSearchMCPCommand,
    "grep": FsGrepCommand,
    "cross": ProjectCrossSearchCommand,
}

_PAGINATED_BACKEND_DISPATCH: dict[str, str] = {
    "fulltext": "_paginated_backend_fulltext",
    "semantic": "_paginated_backend_semantic",
    "grep": "_run_paginated_grep_hook",
    "cross": "_paginated_backend_cross",
    "tree_query": "_paginated_backend_tree_query",
}


class SearchStartCommand(BaseMCPCommand):
    """Start search via selected backend with optional paginated session routing."""

    name = "search_start"
    version = "1.0.0"
    descr = (
        "Start a search using fulltext, semantic, grep, cross, or tree_query backends. "
        "Default behavior matches legacy search commands. Set paginated=true for "
        "SearchSession-backed block results."
    )
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        base: Dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "required": ["project_id", "search_type"],
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "search_type": {
                    "type": "string",
                    "enum": list(SEARCH_TYPES),
                    "description": "Search backend to execute.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query text when required by the selected backend.",
                },
                "grep_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Grep or cross-search pattern list.",
                },
                "xpath": {
                    "type": "string",
                    "description": "XPath-like filter for tree_query backend.",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Optional project-relative path filter.",
                },
                "page_size": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 200,
                },
                "auto_queue_on_inline_timeout": {
                    "type": "boolean",
                    "default": True,
                },
                "inline_timeout_seconds": {
                    "type": "number",
                    "default": 3.0,
                },
                "hard_timeout_seconds": {
                    "type": "number",
                    "default": 120.0,
                },
                "include_preview": {
                    "type": "boolean",
                    "default": False,
                },
                "require_structural_grep": {
                    "type": "boolean",
                    "default": True,
                },
                "scan_all": {
                    "type": "boolean",
                    "default": False,
                },
            },
        }
        return cast(Dict[str, Any], merge_pagination_schema(base))

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return validate params."""
        params = super().validate_params(params)
        search_type = params.get("search_type")
        if search_type not in SEARCH_TYPES:
            raise ValidationError(
                f"{self.name}: unsupported search_type {search_type!r}",
                field="search_type",
                details={"allowed": list(SEARCH_TYPES)},
            )
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    async def execute(self, **kwargs: Any) -> SuccessResult | ErrorResult:
        """Execute the command."""
        try:
            params = self.validate_params(
                {k: v for k, v in kwargs.items() if k != "context"}
            )
        except ValidationError as exc:
            return self._handle_error(exc, "VALIDATION_ERROR", self.name)

        search_type = str(params["search_type"])
        try:
            if params.get("paginated") is True:
                payload = await self._execute_paginated(params, search_type)
                return SuccessResult(data=payload)
            return await self._execute_legacy(params, search_type)
        except NotImplementedError as exc:
            return self._handle_error(exc, "NOT_IMPLEMENTED", self.name)

    async def _execute_legacy(
        self,
        params: Dict[str, Any],
        search_type: str,
    ) -> SuccessResult | ErrorResult:
        """Return execute legacy."""
        if search_type == "tree_query":
            raise NotImplementedError(
                "tree_query legacy backend is not implemented yet"
            )
        command_cls = _LEGACY_COMMAND_BY_TYPE[search_type]
        command = command_cls()
        backend_params = self._backend_params(params, search_type)
        return await command.execute(**backend_params)

    async def _execute_paginated(
        self,
        params: Dict[str, Any],
        search_type: str,
    ) -> dict:
        """Return execute paginated."""
        storage = self._get_shared_storage()
        config_dir = storage.config_dir
        search_id = str(uuid.uuid4())
        layout = provision_search_session_directory(
            config_dir=config_dir,
            search_id=search_id,
        )
        session = SearchSession(
            search_id=search_id,
            state=SearchSessionState.running,
            directory_path=layout.root,
        )
        try:
            first_block_position = await self._dispatch_paginated_backend(
                session=session,
                layout=layout,
                params=params,
                search_type=search_type,
            )
        except Exception:
            shutil.rmtree(layout.root, ignore_errors=True)
            raise

        return cast(
            dict[str, Any],
            maybe_route_paginated(
                params=params,
                legacy_executor=lambda: {},
                session_factory=lambda: session,
                first_block_position=first_block_position,
            ),
        )

    async def _dispatch_paginated_backend(
        self,
        *,
        session: SearchSession,
        layout: SearchSessionDirectoryLayout,
        params: Dict[str, Any],
        search_type: str,
    ) -> Optional[int]:
        """Block until session index and first result block exist."""
        handler_name = _PAGINATED_BACKEND_DISPATCH.get(search_type)
        if handler_name is None:
            raise NotImplementedError(
                f"Paginated search_start backend {search_type!r} is not implemented yet"
            )
        handler = getattr(self, handler_name)
        return cast(Optional[int], await handler(session, layout, params))

    async def _paginated_backend_fulltext(
        self,
        session: SearchSession,
        layout: SearchSessionDirectoryLayout,
        params: Dict[str, Any],
    ) -> Optional[int]:
        """Run paginated fulltext via fulltext_search and publish the first result block."""
        now = time.time()
        request = {
            key: value
            for key, value in params.items()
            if key
            not in {
                "paginated",
                "include_job_id",
                "job_id",
                "block_position",
            }
        }
        manifest = SearchSessionManifest(
            search_id=session.search_id,
            created_at=now,
            last_access_at=now,
            heartbeat_at=now,
            status="running",
            phase="indexed_search",
            request=request,
            metrics=dict(DEFAULT_METRICS),
            process=capture_server_process_identity(),
            block_ready_count=0,
        )
        write_manifest_atomic(layout, manifest)
        initialize_service_metadata(layout, now=now)

        command = FulltextSearchMCPCommand()
        backend_params = self._backend_params(params, "fulltext")
        result = await command.execute(**backend_params)
        if isinstance(result, ErrorResult):
            raise RuntimeError(result.message)

        results = list((result.data or {}).get("results") or [])
        policy = load_session_ttl_policy(self._get_raw_config())
        buffer = RawFindingBuffer(layout.buffer_dir)
        for index, finding in enumerate(results):
            if isinstance(finding, dict):
                buffer.append_finding(f"fulltext-{index:06d}", finding)

        assembler = self._create_block_assembler(layout, policy.max_block_size_bytes)
        assembler.run_until_idle(search_completed=True)

        if (layout.blocks_dir / "block_1.json").is_file():
            return 1
        return None

    async def _paginated_backend_semantic(
        self,
        session: SearchSession,
        layout: SearchSessionDirectoryLayout,
        params: Dict[str, Any],
    ) -> Optional[int]:
        """Run paginated semantic via semantic_search and publish the first result block."""
        now = time.time()
        request = {
            key: value
            for key, value in params.items()
            if key
            not in {
                "paginated",
                "include_job_id",
                "job_id",
                "block_position",
            }
        }
        manifest = SearchSessionManifest(
            search_id=session.search_id,
            created_at=now,
            last_access_at=now,
            heartbeat_at=now,
            status="running",
            phase="indexed_search",
            request=request,
            metrics=dict(DEFAULT_METRICS),
            process=capture_server_process_identity(),
            block_ready_count=0,
        )
        write_manifest_atomic(layout, manifest)
        initialize_service_metadata(layout, now=now)

        command = SemanticSearchMCPCommand()
        backend_params = self._backend_params(params, "semantic")
        result = await command.execute(**backend_params)
        if isinstance(result, ErrorResult):
            raise RuntimeError(result.message)

        results = list((result.data or {}).get("results") or [])
        policy = load_session_ttl_policy(self._get_raw_config())
        buffer = RawFindingBuffer(layout.buffer_dir)
        for index, finding in enumerate(results):
            if isinstance(finding, dict):
                buffer.append_finding(f"semantic-{index:06d}", finding)

        assembler = self._create_block_assembler(layout, policy.max_block_size_bytes)
        assembler.run_until_idle(search_completed=True)

        if (layout.blocks_dir / "block_1.json").is_file():
            return 1
        return None

    async def _paginated_backend_cross(
        self,
        session: SearchSession,
        layout: SearchSessionDirectoryLayout,
        params: Dict[str, Any],
    ) -> Optional[int]:
        """Return paginated backend cross."""
        from .search_paginated_cross import run_paginated_cross

        return await run_paginated_cross(
            command=ProjectCrossSearchCommand(),
            params=params,
            session=session,
            layout=layout,
            raw_config=self._get_raw_config(),
            block_assembler_factory=self._create_block_assembler,
        )

    async def _paginated_backend_tree_query(
        self,
        session: SearchSession,
        layout: SearchSessionDirectoryLayout,
        params: Dict[str, Any],
    ) -> Optional[int]:
        """Return paginated backend tree query."""
        raise NotImplementedError(
            "Paginated search_start backend 'tree_query' is not implemented yet"
        )

    async def _run_paginated_grep_hook(
        self,
        session: SearchSession,
        layout: SearchSessionDirectoryLayout,
        params: Dict[str, Any],
    ) -> Optional[int]:
        """Run paginated grep via fs_ggrep and publish the first result block."""
        now = time.time()
        request = {
            key: value
            for key, value in params.items()
            if key
            not in {
                "paginated",
                "include_job_id",
                "job_id",
                "block_position",
            }
        }
        manifest = SearchSessionManifest(
            search_id=session.search_id,
            created_at=now,
            last_access_at=now,
            heartbeat_at=now,
            status="running",
            phase="indexed_search",
            request=request,
            metrics=dict(DEFAULT_METRICS),
            process=capture_server_process_identity(),
            block_ready_count=0,
        )
        write_manifest_atomic(layout, manifest)
        initialize_service_metadata(layout, now=now)

        require_structural = bool(params.get("require_structural_grep", True))
        grep_mode = (
            GrepSearchMode.structural
            if require_structural
            else GrepSearchMode.classic_line
        )
        mode_params = grep_mode_to_fs_ggrep_params(grep_mode)
        pattern = self._grep_pattern_from_params(params)

        grep_kwargs: Dict[str, Any] = {
            "project_id": params["project_id"],
            "pattern": pattern,
            "file_pattern": params.get("file_pattern"),
            "scan_all": bool(params.get("scan_all", False)),
            "auto_queue_on_inline_timeout": bool(
                params.get("auto_queue_on_inline_timeout", True)
            ),
            "inline_timeout_seconds": params.get("inline_timeout_seconds", 3.0),
            "hard_timeout_seconds": params.get("hard_timeout_seconds", 120.0),
            "fast_text_only": mode_params.fast_text_only,
            "enrich_blocks": mode_params.enrich_blocks,
        }
        grep_kwargs = {
            key: value for key, value in grep_kwargs.items() if value is not None
        }

        command = FsGrepCommand()
        result = await command.execute(**grep_kwargs)
        if isinstance(result, ErrorResult):
            raise RuntimeError(result.message)

        matches = list((result.data or {}).get("matches") or [])
        policy = load_session_ttl_policy(self._get_raw_config())
        buffer = RawFindingBuffer(layout.buffer_dir)
        for index, match in enumerate(matches):
            if isinstance(match, dict):
                buffer.append_finding(f"grep-{index:06d}", match)

        assembler = self._create_block_assembler(layout, policy.max_block_size_bytes)
        assembler.run_until_idle(search_completed=True)

        if (layout.blocks_dir / "block_1.json").is_file():
            return 1
        return None

    def _create_block_assembler(
        self,
        layout: SearchSessionDirectoryLayout,
        max_block_size_bytes: int,
    ) -> BlockAssembler:
        """Return create block assembler."""

        def append_index_entry(position: int, completeness: str) -> None:
            """Return append index entry."""
            block_path = layout.blocks_dir / f"block_{position}.json"
            size_bytes = block_path.stat().st_size if block_path.is_file() else 0
            append_block_entry(
                layout.index_path,
                position=position,
                size_bytes=size_bytes,
                completeness=completeness,
            )

        def update_manifest_metrics(metrics: dict[str, int]) -> None:
            """Return update manifest metrics."""

            def mutator(current: SearchSessionManifest) -> SearchSessionManifest:
                """Return mutator."""
                next_metrics = dict(current.metrics)
                next_metrics["produced_results"] = next_metrics.get(
                    "produced_results", 0
                ) + int(metrics.get("produced_results", 0))
                next_metrics["written_blocks"] = next_metrics.get(
                    "written_blocks", 0
                ) + int(metrics.get("written_blocks", 0))
                return replace(
                    current,
                    metrics=next_metrics,
                    block_ready_count=current.block_ready_count
                    + int(metrics.get("written_blocks", 0)),
                )

            update_manifest_atomic(layout, mutator)

        return BlockAssembler(
            layout,
            RawFindingBuffer(layout.buffer_dir),
            max_block_size_bytes,
            append_index_entry=append_index_entry,
            update_manifest_metrics=update_manifest_metrics,
        )

    @staticmethod
    def _grep_pattern_from_params(params: Dict[str, Any]) -> str:
        """Return grep pattern from params."""
        query = params.get("query")
        if isinstance(query, str) and query.strip():
            return query.strip()
        patterns = params.get("grep_patterns")
        if isinstance(patterns, list):
            for item in patterns:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        raise ValidationError(
            "grep paginated search requires query or grep_patterns",
            field="query",
        )

    @staticmethod
    def _backend_params(params: Dict[str, Any], search_type: str) -> Dict[str, Any]:
        """Return backend params."""
        passthrough_keys = {
            key
            for key in params
            if key
            not in {
                "paginated",
                "include_job_id",
                "job_id",
                "block_position",
                "search_type",
                "page_size",
            }
        }
        backend_params = {key: params[key] for key in passthrough_keys}
        schema_fn = _PAGINATED_SCHEMA_BY_TYPE.get(search_type)
        if schema_fn is not None:
            _ = schema_fn()
        return backend_params

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
            "detailed_description": (
                "search_start routes to existing search backends. When paginated is false "
                "(default), behavior matches the underlying legacy command. When paginated "
                "is true, execution uses SearchSession directories and returns a job handoff."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID.",
                    "type": "string",
                    "required": True,
                },
                "search_type": {
                    "description": "Backend selector.",
                    "type": "string",
                    "required": True,
                    "enum": list(SEARCH_TYPES),
                },
                "paginated": {
                    "description": "Opt in to SearchSession paginated execution.",
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Legacy fulltext search",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "search_type": "fulltext",
                        "query": "MyClass",
                    },
                    "explanation": "Runs fulltext_search-compatible inline results.",
                }
            ],
            "error_cases": {
                "NOT_IMPLEMENTED": {
                    "description": "Paginated or tree_query backend not available yet.",
                    "message": "Backend not implemented",
                    "solution": "Use paginated=false or a supported search_type.",
                }
            },
            "return_value": {
                "success": {
                    "description": "Legacy payload or paginated handoff.",
                    "data": {
                        "job_id": "Present when paginated=true",
                        "index_url": "HTTP index path template when paginated=true",
                    },
                },
                "error": {
                    "description": "Validation or backend failure.",
                    "code": "Error code string",
                    "message": "Human-readable message",
                },
            },
            "best_practices": [
                "Leave paginated=false for legacy unbounded responses.",
                "Use list_projects to resolve project_id before calling search_start.",
            ],
        }
