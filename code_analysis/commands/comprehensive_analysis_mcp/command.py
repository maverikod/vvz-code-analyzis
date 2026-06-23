"""
MCP command wrapper: comprehensive_analysis.

Comprehensive code analysis combining multiple analysis types.
Lives in package comprehensive_analysis_mcp; schema and metadata in sibling modules.
Single-file and batch execution live in execute_single and execute_batch.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional, Union

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.comprehensive_analyzer import ComprehensiveAnalyzer
from ...core.constants import DEFAULT_MAX_FILE_LINES
from ...core.exceptions import ValidationError
from ..base_mcp_command import BaseMCPCommand
from . import schema
from .execute_batch import run_batch
from .execute_single import run_single_file
from .metadata import get_metadata
from .project_integrity_phase import maybe_run_project_integrity_checks
from .quality_tools import probe_required_tools

logger = logging.getLogger(__name__)


class ComprehensiveAnalysisMCPCommand(BaseMCPCommand):
    """Comprehensive code analysis command combining multiple analysis types."""

    name = "comprehensive_analysis"
    version = "1.0.0"
    descr = "Comprehensive code analysis (placeholders, stubs, duplicates, long files, missing docstrings, etc.)"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return schema.get_schema(cls)

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate params and reject unknown project_id before queuing."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        depth = int(params.get("max_import_chain_depth", 10))
        if depth < 2 or depth > 10:
            raise ValidationError(
                "max_import_chain_depth must be between 2 and 10",
                field="max_import_chain_depth",
            )
        return params

    async def execute(
        self,
        project_id: str,
        file_path: Optional[str] = None,
        max_lines: int = DEFAULT_MAX_FILE_LINES,
        check_placeholders: bool = True,
        check_stubs: bool = True,
        check_empty_methods: bool = True,
        check_imports: bool = True,
        check_long_files: bool = True,
        check_duplicates: bool = True,
        check_flake8: bool = True,
        check_mypy: bool = True,
        check_black: bool = False,
        check_isort: bool = False,
        check_bandit: bool = False,
        check_docstrings: bool = True,
        duplicate_min_lines: int = 5,
        duplicate_min_similarity: float = 0.8,
        mypy_config_file: Optional[str] = None,
        bandit_config_file: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        check_missing_files_on_disk: bool = True,
        check_circular_imports: bool = True,
        max_import_chain_depth: int = 10,
        **kwargs,
    ) -> Union[SuccessResult, ErrorResult]:
        """Execute comprehensive analysis."""
        from ...core.progress_tracker import get_progress_tracker_from_context

        extra = dict(kwargs)
        context = extra.pop("context", None) or {}
        params: Dict[str, Any] = {
            "project_id": project_id,
            "file_path": file_path,
            "max_lines": max_lines,
            "check_placeholders": check_placeholders,
            "check_stubs": check_stubs,
            "check_empty_methods": check_empty_methods,
            "check_imports": check_imports,
            "check_long_files": check_long_files,
            "check_duplicates": check_duplicates,
            "check_flake8": check_flake8,
            "check_mypy": check_mypy,
            "check_black": check_black,
            "check_isort": check_isort,
            "check_bandit": check_bandit,
            "check_docstrings": check_docstrings,
            "duplicate_min_lines": duplicate_min_lines,
            "duplicate_min_similarity": duplicate_min_similarity,
            "mypy_config_file": mypy_config_file,
            "bandit_config_file": bandit_config_file,
            "limit": limit,
            "offset": offset,
        }
        params.update(extra)
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return self._handle_error(e, "VALIDATION_ERROR", "comprehensive_analysis")
        project_id = params["project_id"]
        file_path = params.get("file_path")
        max_lines = int(params.get("max_lines", DEFAULT_MAX_FILE_LINES))
        check_placeholders = bool(params.get("check_placeholders", True))
        check_stubs = bool(params.get("check_stubs", True))
        check_empty_methods = bool(params.get("check_empty_methods", True))
        check_imports = bool(params.get("check_imports", True))
        check_long_files = bool(params.get("check_long_files", True))
        check_duplicates = bool(params.get("check_duplicates", True))
        check_flake8 = bool(params.get("check_flake8", True))
        check_mypy = bool(params.get("check_mypy", True))
        check_black = bool(params.get("check_black", False))
        check_isort = bool(params.get("check_isort", False))
        check_bandit = bool(params.get("check_bandit", False))
        check_docstrings = bool(params.get("check_docstrings", True))
        duplicate_min_lines = int(params.get("duplicate_min_lines", 5))
        duplicate_min_similarity = float(params.get("duplicate_min_similarity", 0.8))
        mypy_config_file = params.get("mypy_config_file")
        bandit_config_file = params.get("bandit_config_file")
        limit = params.get("limit")
        offset = int(params.get("offset", 0))
        check_missing_files_on_disk = bool(
            params.get("check_missing_files_on_disk", True)
        )
        check_circular_imports = bool(params.get("check_circular_imports", True))
        max_import_chain_depth = int(params.get("max_import_chain_depth", 10))

        # Hard-fail contract (A-HARDFAIL): probe requested quality tools once, up
        # front, before any file iteration. A requested check whose tool is
        # missing aborts here with QUALITY_TOOL_UNAVAILABLE instead of returning
        # a bogus "clean" result.
        tool_error = probe_required_tools(
            {
                "check_flake8": check_flake8,
                "check_mypy": check_mypy,
                "check_black": check_black,
                "check_isort": check_isort,
                "check_bandit": check_bandit,
            }
        )
        if tool_error is not None:
            return tool_error

        t_start = time.perf_counter()
        progress_tracker = get_progress_tracker_from_context(context)

        root_path = self._resolve_project_root(project_id)

        # Setup dedicated log file for comprehensive analysis
        analysis_logger = logging.getLogger("comprehensive_analysis")
        analysis_logger.setLevel(logging.INFO)

        # Remove existing handlers to avoid duplicates
        analysis_logger.handlers = []

        # Create logs directory if it doesn't exist
        logs_dir = root_path / "logs"
        logs_dir.mkdir(exist_ok=True)

        # Create rotating file handler for comprehensive_analysis.log
        log_file = logs_dir / "comprehensive_analysis.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        analysis_logger.addHandler(file_handler)
        analysis_logger.propagate = False  # Don't propagate to root logger

        def log_timing(phase: str, t0: float) -> float:
            elapsed = time.perf_counter() - t0
            analysis_logger.info("[TIMING] phase=%s elapsed_sec=%.4f", phase, elapsed)
            return time.perf_counter()

        try:
            if progress_tracker:
                progress_tracker.set_status("running")
                progress_tracker.set_description("Analysis: resolving project root...")
                progress_tracker.set_progress(0)

            log_timing("init_resolve_root", t_start)
            t_after = time.perf_counter()

            if progress_tracker:
                progress_tracker.set_description("Analysis: opening database...")
                progress_tracker.set_progress(0)

            db = self._open_database()
            t_after = log_timing("db_open", t_after)
            proj_id = project_id

            analyzer = ComprehensiveAnalyzer(max_lines=max_lines)
            results: Dict[str, Any] = {
                "placeholders": [],
                "stubs": [],
                "empty_methods": [],
                "imports_not_at_top": [],
                "long_files": [],
                "duplicates": [],
                "flake8_errors": [],
                "mypy_errors": [],
                "black_findings": [],
                "isort_findings": [],
                "bandit_findings": [],
                "missing_docstrings": [],
                "summary": {},
                "project_integrity": {},
            }

            project_integrity = maybe_run_project_integrity_checks(
                db,
                project_id,
                root_path,
                check_missing_files=check_missing_files_on_disk,
                check_circular_imports=check_circular_imports,
                max_import_chain_depth=max_import_chain_depth,
                analysis_logger=analysis_logger,
            )
            results["project_integrity"] = project_integrity

            # Statistics for incremental analysis
            files_analyzed = 0
            files_skipped = 0
            files_total = 0

            # Resolve mypy config file path if provided
            mypy_config = None
            if mypy_config_file:
                mypy_config = Path(mypy_config_file)
                if not mypy_config.is_absolute():
                    mypy_config = root_path / mypy_config

            bandit_config = None
            if bandit_config_file:
                bandit_config = Path(bandit_config_file)
                if not bandit_config.is_absolute():
                    bandit_config = root_path / bandit_config

            ctx: Dict[str, Any] = {
                "db": db,
                "root_path": root_path,
                "proj_id": proj_id,
                "analysis_logger": analysis_logger,
                "log_timing": log_timing,
                "progress_tracker": progress_tracker,
                "analyzer": analyzer,
                "results": results,
                "mypy_config": mypy_config,
                "bandit_config": bandit_config,
                "t_start": t_start,
                "file_path": file_path,
                "max_lines": max_lines,
                "check_placeholders": check_placeholders,
                "check_stubs": check_stubs,
                "check_empty_methods": check_empty_methods,
                "check_imports": check_imports,
                "check_long_files": check_long_files,
                "check_duplicates": check_duplicates,
                "check_flake8": check_flake8,
                "check_mypy": check_mypy,
                "check_black": check_black,
                "check_isort": check_isort,
                "check_bandit": check_bandit,
                "check_docstrings": check_docstrings,
                "duplicate_min_lines": duplicate_min_lines,
                "duplicate_min_similarity": duplicate_min_similarity,
                "limit": limit,
                "offset": offset,
                "check_missing_files_on_disk": check_missing_files_on_disk,
                "check_circular_imports": check_circular_imports,
                "max_import_chain_depth": max_import_chain_depth,
            }

            if file_path:
                return await run_single_file(self, ctx)
            return await run_batch(self, ctx)
        except Exception as e:
            analysis_logger.error(f"Comprehensive analysis failed: {e}", exc_info=True)

            for handler in analysis_logger.handlers[:]:
                handler.close()
                analysis_logger.removeHandler(handler)

            return self._handle_error(
                e, "COMPREHENSIVE_ANALYSIS_ERROR", "comprehensive_analysis"
            )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_metadata(cls)
