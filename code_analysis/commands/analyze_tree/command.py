"""
MCP command: analyze_tree.

One read-only command that analyzes a sub-tree of a watched project (one or more
directory roots) under a selected ``mode`` lens. Thin by design: it validates
params, resolves the project root + DB handle, delegates the shared core and mode
post-processing to the service, then formats the result. See the package docstring
for the design (one shared core, several lenses).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ...core.exceptions import ValidationError
from .formatters import format_output
from .modes import DEFAULT_KEEP_SEEDS, DEFAULT_PARAMETERIZE_SEEDS
from .service import analyze_tree_json

logger = logging.getLogger(__name__)

MODES = ("package_boundary", "dependencies", "structure", "cycles")
FORMATS = ("json", "dot", "markdown")
DEFAULT_LIMIT = 50000


class AnalyzeTreeMCPCommand(BaseMCPCommand):
    """Analyze a project sub-tree under one of several lenses (modes).

    Modes: ``package_boundary`` (extraction analysis), ``dependencies`` (relation
    graph), ``structure`` (composition), ``cycles`` (circular-import defects).
    Read-only: never mutates project sources, sidecars, or the DB.
    """

    name = "analyze_tree"
    version = "1.0.0"
    descr = (
        "Analyze a project sub-tree under a mode lens: package_boundary, "
        "dependencies, structure, or cycles (json/dot/markdown)"
    )
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["AnalyzeTreeMCPCommand"]) -> Dict[str, Any]:
        """JSON schema for analyze_tree parameters (atom A-CMD)."""
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "roots": {
                    "type": "array",
                    "description": (
                        "Project-relative directory prefixes defining the sub-tree "
                        "(e.g. ['core/cst_tree/']). At least one."
                    ),
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "mode": {
                    "type": "string",
                    "description": (
                        "Analysis lens: 'package_boundary' (extraction), "
                        "'dependencies' (relation graph), 'structure' (composition), "
                        "or 'cycles' (circular imports)."
                    ),
                    "enum": list(MODES),
                },
                "include_stdlib": {
                    "type": "boolean",
                    "description": "Include stdlib in dependency/outbound output.",
                    "default": False,
                },
                "with_verdict": {
                    "type": "boolean",
                    "description": (
                        "package_boundary only: attach an extraction verdict "
                        "(pull_in / keep_in_server / parameterize) per project leak."
                    ),
                    "default": False,
                },
                "format": {
                    "type": "string",
                    "description": "Output format.",
                    "enum": list(FORMATS),
                    "default": "json",
                },
                "limit": {
                    "type": "integer",
                    "description": "Edge cap (1–50000). Default 50000.",
                    "default": DEFAULT_LIMIT,
                    "minimum": 1,
                    "maximum": 50000,
                },
            },
            "required": ["project_id", "roots", "mode"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Schema validation + limit range + project existence."""
        params = super().validate_params(params)
        limit = params.get("limit")
        if limit is not None and not (1 <= limit <= 50000):
            raise ValidationError(
                f"{self.name}: parameter 'limit' must be in 1..50000, got {limit!r}",
                field="limit",
                details={"minimum": 1, "maximum": 50000},
            )
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    def _dirty_seeds(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Read tunable verdict seeds from config, falling back to defaults."""
        try:
            cfg = BaseMCPCommand._get_raw_config()
            node = (cfg.get("code_analysis", {}) or {}).get("analyze_tree", {}) or {}
            keep = node.get("dirty_module_seeds")
            param = node.get("parameterize_module_seeds")
            keep_seeds = tuple(keep) if isinstance(keep, list) and keep else DEFAULT_KEEP_SEEDS
            param_seeds = (
                tuple(param) if isinstance(param, list) and param else DEFAULT_PARAMETERIZE_SEEDS
            )
            return keep_seeds, param_seeds
        except Exception:
            return DEFAULT_KEEP_SEEDS, DEFAULT_PARAMETERIZE_SEEDS

    async def execute(
        self: "AnalyzeTreeMCPCommand",
        project_id: str,
        roots: Optional[List[str]] = None,
        mode: Optional[str] = None,
        include_stdlib: bool = False,
        with_verdict: bool = False,
        format: str = "json",
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Analyze the sub-tree and return the selected mode's output."""
        call_params: Dict[str, Any] = {
            "project_id": project_id,
            "roots": roots,
            "mode": mode,
            "include_stdlib": include_stdlib,
            "with_verdict": with_verdict,
            "format": format,
            "limit": limit,
        }
        call_params.update(kwargs)
        try:
            call_params = self.validate_params(call_params)
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None) or {"field": getattr(e, "field", None)},
            )

        project_id = call_params["project_id"]
        roots = list(call_params["roots"])
        mode = str(call_params["mode"])
        include_stdlib = bool(call_params.get("include_stdlib") or False)
        with_verdict = bool(call_params.get("with_verdict") or False)
        fmt = str(call_params.get("format") or "json")
        edge_limit = int(call_params["limit"]) if call_params.get("limit") is not None else DEFAULT_LIMIT

        try:
            project_root = self._resolve_project_root(project_id)
            keep_seeds, param_seeds = self._dirty_seeds()
            db = self._open_database()
            try:
                data = analyze_tree_json(
                    db=db,
                    project_id=project_id,
                    project_root=project_root,
                    roots=roots,
                    mode=mode,
                    include_stdlib=include_stdlib,
                    with_verdict=with_verdict,
                    limit=edge_limit,
                    keep_seeds=keep_seeds,
                    parameterize_seeds=param_seeds,
                )
            finally:
                db.disconnect()
            return SuccessResult(data=format_output(data, fmt))
        except Exception as e:
            return self._handle_error(e, "ANALYZE_TREE_ERROR", "analyze_tree")

    @classmethod
    def metadata(cls: type["AnalyzeTreeMCPCommand"]) -> Dict[str, Any]:
        """Detailed command metadata for AI models / help."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "Read-only analysis of a project sub-tree (one or more directory "
                "roots) under a selected mode lens. A shared core enumerates real "
                "files (disk = existence truth), applies the checksum staleness gate "
                "(ChecksumSyncPolicy C-006) so analysis never runs on stale rows, and "
                "builds a module-resolved relation graph once; each mode is a "
                "post-processor over that core.\n\n"
                "Modes:\n"
                "- package_boundary: extraction analysis — internal_files, outbound "
                "(project BLOCKER list / third_party / stdlib), inbound (external "
                "callers to replace), and an optional extraction verdict.\n"
                "- dependencies: plain relation graph (internal vs external); no cycles.\n"
                "- structure: composition (modules/classes/functions); no quality scoring.\n"
                "- cycles: circular-import chains within the sub-tree, with cycles_found.\n\n"
                "Out of scope (use the dedicated commands): complexity, long files, "
                "size scoring → comprehensive_analysis / analyze_complexity / "
                "list_long_files."
            ),
            "parameters": {
                "project_id": {"type": "string", "required": True, "description": "Watched project UUID."},
                "roots": {
                    "type": "array",
                    "required": True,
                    "description": "Project-relative directory prefixes (>=1).",
                    "examples": [["core/cst_tree/"], ["commands/analyze_tree/"]],
                },
                "mode": {"type": "string", "required": True, "examples": list(MODES)},
                "include_stdlib": {"type": "boolean", "required": False, "default": False},
                "with_verdict": {"type": "boolean", "required": False, "default": False},
                "format": {"type": "string", "required": False, "examples": list(FORMATS)},
                "limit": {"type": "integer", "required": False, "default": DEFAULT_LIMIT},
            },
            "return_value": {
                "success": {
                    "description": "mode, roots, staleness, and mode-specific blocks.",
                },
                "error": {"code": "ANALYZE_TREE_ERROR | VALIDATION_ERROR"},
            },
        }
