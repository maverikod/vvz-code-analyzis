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
from ..base_mcp_command import BaseMCPCommand
from . import schema
from .execute_batch import run_batch
from .execute_single import run_single_file
from .metadata import get_metadata

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
        check_docstrings: bool = True,
        duplicate_min_lines: int = 5,
        duplicate_min_similarity: float = 0.8,
        mypy_config_file: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        **kwargs,
    ) -> Union[SuccessResult, ErrorResult]:
        """Execute comprehensive analysis."""
        from ...core.progress_tracker import get_progress_tracker_from_context

        t_start = time.perf_counter()
        progress_tracker = get_progress_tracker_from_context(
            kwargs.get("context") or {}
        )

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
            log_timing("init_resolve_root", t_start)
            t_after = time.perf_counter()
            db = self._open_database()
            t_after = log_timing("db_open", t_after)
            proj_id = project_id

            if progress_tracker:
                progress_tracker.set_status("running")
                progress_tracker.set_description(
                    "Initializing comprehensive analysis..."
                )
                progress_tracker.set_progress(0)

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
                "missing_docstrings": [],
                "summary": {},
            }

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
                "check_docstrings": check_docstrings,
                "duplicate_min_lines": duplicate_min_lines,
                "duplicate_min_similarity": duplicate_min_similarity,
                "limit": limit,
                "offset": offset,
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
