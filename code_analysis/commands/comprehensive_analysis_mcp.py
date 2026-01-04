"""
MCP command wrapper: comprehensive_analysis.

Comprehensive code analysis combining multiple analysis types:
- Placeholders (TODO, FIXME, etc.)
- Stubs (pass, ellipsis, NotImplementedError)
- Empty methods (excluding abstract)
- Imports not at top of file
- Long files
- Code duplicates

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.comprehensive_analysis_runner import (
    ComprehensiveAnalysisConfig,
    run_comprehensive_analysis,
)
from .base_mcp_command import BaseMCPCommand

logger = logging.getLogger(__name__)


class ComprehensiveAnalysisMCPCommand(BaseMCPCommand):
    """
    Comprehensive code analysis command combining multiple analysis types.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Human-readable description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether the command is executed via queue.
    """

    name = "comprehensive_analysis"
    version = "1.0.0"
    descr = "Comprehensive code analysis (placeholders, stubs, duplicates, long files, etc.)"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Returns:
            JSON schema for command parameters.
        """
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "description": (
                "Comprehensive code analysis combining multiple analysis types: "
                "placeholders, stubs, empty methods, imports not at top, long files, "
                "duplicates, flake8 linting, mypy type checking. "
                "This is a long-running command and is executed via queue."
            ),
            "properties": {
                **base_props,
                "file_path": {
                    "type": "string",
                    "description": "Optional path to specific file to analyze",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines threshold for long files",
                    "default": 400,
                },
                "check_placeholders": {
                    "type": "boolean",
                    "description": "Check for placeholders (TODO, FIXME, etc.)",
                    "default": True,
                },
                "check_stubs": {
                    "type": "boolean",
                    "description": "Check for stub functions/methods",
                    "default": True,
                },
                "check_empty_methods": {
                    "type": "boolean",
                    "description": "Check for empty methods",
                    "default": True,
                },
                "check_imports": {
                    "type": "boolean",
                    "description": "Check for imports not at top of file",
                    "default": True,
                },
                "check_long_files": {
                    "type": "boolean",
                    "description": "Check for long files",
                    "default": True,
                },
                "check_duplicates": {
                    "type": "boolean",
                    "description": "Check for code duplicates",
                    "default": True,
                },
                "check_flake8": {
                    "type": "boolean",
                    "description": "Check code with flake8 linter",
                    "default": True,
                },
                "check_mypy": {
                    "type": "boolean",
                    "description": "Check code with mypy type checker",
                    "default": True,
                },
                "duplicate_min_lines": {
                    "type": "integer",
                    "description": "Minimum lines for duplicate detection",
                    "default": 5,
                },
                "duplicate_min_similarity": {
                    "type": "number",
                    "description": "Minimum similarity for duplicates",
                    "default": 0.8,
                },
                "mypy_config_file": {
                    "type": "string",
                    "description": "Optional path to mypy config file",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: Optional[str] = None,
        project_id: Optional[str] = None,
        max_lines: int = 400,
        check_placeholders: bool = True,
        check_stubs: bool = True,
        check_empty_methods: bool = True,
        check_imports: bool = True,
        check_long_files: bool = True,
        check_duplicates: bool = True,
        check_flake8: bool = True,
        check_mypy: bool = True,
        duplicate_min_lines: int = 5,
        duplicate_min_similarity: float = 0.8,
        mypy_config_file: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        """Execute comprehensive analysis.

        Args:
            self: Command instance.
            root_dir: Project root directory.
            file_path: Optional path to specific file to analyze.
            project_id: Optional project UUID.
            max_lines: Maximum lines threshold for long files.
            check_placeholders: Check for placeholders.
            check_stubs: Check for stubs.
            check_empty_methods: Check for empty methods.
            check_imports: Check for imports not at top.
            check_long_files: Check for long files.
            check_duplicates: Check for duplicates.
            check_flake8: Check with flake8 linter.
            check_mypy: Check with mypy type checker.
            duplicate_min_lines: Minimum lines for duplicates.
            duplicate_min_similarity: Minimum similarity for duplicates.
            mypy_config_file: Optional path to mypy config file.

        Returns:
            SuccessResult with comprehensive analysis results.
        """
        from ..core.progress_tracker import get_progress_tracker_from_context

        progress_tracker = get_progress_tracker_from_context(
            kwargs.get("context") or {}
        )

        # Setup dedicated log file for comprehensive analysis
        analysis_logger = logging.getLogger("comprehensive_analysis")
        analysis_logger.setLevel(logging.INFO)

        # Remove existing handlers to avoid duplicates
        analysis_logger.handlers = []

        # Create logs directory if it doesn't exist
        root_path = self._validate_root_dir(root_dir)
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

        try:
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)

            if not proj_id:
                db.close()
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            mypy_config: Optional[Path] = None
            if mypy_config_file:
                mypy_config = Path(mypy_config_file)
                if not mypy_config.is_absolute():
                    mypy_config = root_path / mypy_config

            config = ComprehensiveAnalysisConfig(
                max_lines=max_lines,
                check_placeholders=check_placeholders,
                check_stubs=check_stubs,
                check_empty_methods=check_empty_methods,
                check_imports=check_imports,
                check_long_files=check_long_files,
                check_duplicates=check_duplicates,
                check_flake8=check_flake8,
                check_mypy=check_mypy,
                duplicate_min_lines=duplicate_min_lines,
                duplicate_min_similarity=duplicate_min_similarity,
                mypy_config=mypy_config,
                exclude_dir_names=("test_data",),
            )

            file_path_obj: Optional[Path] = None
            if file_path:
                file_path_obj = self._validate_file_path(file_path, root_path)
                if not file_path_obj.exists():
                    db.close()
                    return ErrorResult(message="File not found", code="FILE_NOT_FOUND")

                if file_path_obj.suffix != ".py":
                    db.close()
                    return ErrorResult(
                        message="Only Python (.py) files are supported for comprehensive_analysis",
                        code="UNSUPPORTED_FILE_TYPE",
                        details={"file_path": str(file_path_obj)},
                    )

            results = run_comprehensive_analysis(
                root_path=root_path,
                db=db,
                project_id=proj_id,
                file_path=file_path_obj,
                config=config,
                progress_tracker=progress_tracker,
                analysis_logger=analysis_logger,
            )

            db.close()

            if progress_tracker:
                progress_tracker.set_status("completed")
                progress_tracker.set_description("Analysis completed")
                progress_tracker.set_progress(100)

            # Log completion
            analysis_logger.info(
                f"Comprehensive analysis completed. Summary: {results['summary']}"
            )

            # Clean up handler
            for handler in analysis_logger.handlers[:]:
                handler.close()
                analysis_logger.removeHandler(handler)

            return SuccessResult(data=results)
        except Exception as e:
            # Log error to analysis log
            analysis_logger.error(f"Comprehensive analysis failed: {e}", exc_info=True)

            # Clean up handler
            for handler in analysis_logger.handlers[:]:
                handler.close()
                analysis_logger.removeHandler(handler)

            return self._handle_error(
                e, "COMPREHENSIVE_ANALYSIS_ERROR", "comprehensive_analysis"
            )
