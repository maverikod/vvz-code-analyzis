"""
MCP command wrapper: comprehensive_analysis.

Comprehensive code analysis combining multiple analysis types:
- Placeholders (TODO, FIXME, etc.)
- Stubs (pass, ellipsis, NotImplementedError)
- Empty methods (excluding abstract)
- Imports not at top of file
- Long files
- Code duplicates
- Missing docstrings (files, classes, methods, functions)

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.comprehensive_analyzer import ComprehensiveAnalyzer
from ..core.duplicate_detector import DuplicateDetector
from .base_mcp_command import BaseMCPCommand

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
                "duplicates, missing docstrings, flake8 linting, mypy type checking. "
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
                "check_docstrings": {
                    "type": "boolean",
                    "description": "Check for missing docstrings (files, classes, methods)",
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
        check_docstrings: bool = True,
        duplicate_min_lines: int = 5,
        duplicate_min_similarity: float = 0.8,
        mypy_config_file: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        """Execute comprehensive analysis.

        Args:
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
            check_docstrings: Check for missing docstrings.
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

            # Resolve mypy config file path if provided
            mypy_config = None
            if mypy_config_file:
                mypy_config = Path(mypy_config_file)
                if not mypy_config.is_absolute():
                    mypy_config = root_path / mypy_config

            if file_path:
                # Analyze specific file
                file_path_obj = self._validate_file_path(file_path, root_path)
                if not file_path_obj.exists():
                    db.close()
                    return ErrorResult(message="File not found", code="FILE_NOT_FOUND")

                rel_path = str(file_path_obj.relative_to(root_path))
                logger.info(f"Analyzing single file: {rel_path}")
                analysis_logger.info(f"Starting analysis of single file: {rel_path}")
                source_code = file_path_obj.read_text(encoding="utf-8")

                # Run all checks
                if check_placeholders:
                    placeholders = analyzer.find_placeholders(
                        file_path_obj, source_code
                    )
                    for p in placeholders:
                        p["file_path"] = rel_path
                    results["placeholders"] = placeholders

                if check_stubs:
                    stubs = analyzer.find_stubs(file_path_obj, source_code)
                    for s in stubs:
                        s["file_path"] = rel_path
                    results["stubs"] = stubs

                if check_empty_methods:
                    empty_methods = analyzer.find_empty_methods(
                        file_path_obj, source_code
                    )
                    for m in empty_methods:
                        m["file_path"] = rel_path
                    results["empty_methods"] = empty_methods

                if check_imports:
                    imports_not_at_top = analyzer.find_imports_not_at_top(
                        file_path_obj, source_code
                    )
                    for imp in imports_not_at_top:
                        imp["file_path"] = rel_path
                    results["imports_not_at_top"] = imports_not_at_top

                if check_duplicates:
                    detector = DuplicateDetector(
                        min_lines=duplicate_min_lines,
                        min_similarity=duplicate_min_similarity,
                        use_semantic=False,
                    )
                    duplicates = detector.find_duplicates_in_file(str(file_path_obj))
                    for group in duplicates:
                        for occ in group["occurrences"]:
                            occ["file_path"] = rel_path
                    results["duplicates"] = duplicates

                if check_flake8:
                    flake8_result = analyzer.check_flake8(file_path_obj)
                    if not flake8_result["success"]:
                        flake8_result["file_path"] = rel_path
                        results["flake8_errors"].append(flake8_result)

                if check_mypy:
                    mypy_result = analyzer.check_mypy(file_path_obj, mypy_config)
                    if not mypy_result["success"]:
                        mypy_result["file_path"] = rel_path
                        results["mypy_errors"].append(mypy_result)

                if check_docstrings:
                    missing_docstrings = analyzer.find_missing_docstrings(
                        file_path_obj, source_code
                    )
                    for d in missing_docstrings:
                        d["file_path"] = rel_path
                    results["missing_docstrings"] = missing_docstrings

            else:
                # Analyze all files in ALL projects (not just one project)
                files = db._fetchall(
                    "SELECT id, path, lines FROM files WHERE deleted = 0",
                )

                files_total = len(files)
                analysis_logger.info(
                    f"Starting comprehensive analysis: {files_total} files to analyze"
                )
                if progress_tracker:
                    progress_tracker.set_description(
                        f"Analyzing {files_total} files..."
                    )
                    progress_tracker.set_progress(0)

                all_placeholders: List[Dict[str, Any]] = []
                all_stubs: List[Dict[str, Any]] = []
                all_empty_methods: List[Dict[str, Any]] = []
                all_imports_not_at_top: List[Dict[str, Any]] = []
                all_duplicates: List[Dict[str, Any]] = []
                all_flake8_errors: List[Dict[str, Any]] = []
                all_mypy_errors: List[Dict[str, Any]] = []
                all_missing_docstrings: List[Dict[str, Any]] = []
                file_records: List[Dict[str, Any]] = []

                last_percent = -1
                for idx, file_record in enumerate(files):
                    file_path_str = file_record["path"]

                    # Resolve full path
                    if Path(file_path_str).is_absolute():
                        full_path = Path(file_path_str)
                    else:
                        full_path = root_path / file_path_str

                    if not full_path.exists() or not full_path.is_file():
                        logger.debug(f"Skipping non-existent file: {file_path_str}")
                        continue

                    try:
                        source_code = full_path.read_text(encoding="utf-8")
                    except Exception as e:
                        logger.warning(f"Failed to read file {file_path_str}: {e}")
                        continue

                    file_records.append(
                        {"path": file_path_str, "lines": file_record.get("lines", 0)}
                    )

                    # Log each processed file
                    logger.info(f"Analyzing file {idx + 1}/{files_total}: {file_path_str}")
                    analysis_logger.info(f"Analyzing file {idx + 1}/{files_total}: {file_path_str}")

                    # Run checks
                    if check_placeholders:
                        placeholders = analyzer.find_placeholders(
                            full_path, source_code
                        )
                        for p in placeholders:
                            p["file_path"] = file_path_str
                        all_placeholders.extend(placeholders)

                    if check_stubs:
                        stubs = analyzer.find_stubs(full_path, source_code)
                        for s in stubs:
                            s["file_path"] = file_path_str
                        all_stubs.extend(stubs)

                    if check_empty_methods:
                        empty_methods = analyzer.find_empty_methods(
                            full_path, source_code
                        )
                        for m in empty_methods:
                            m["file_path"] = file_path_str
                        all_empty_methods.extend(empty_methods)

                    if check_imports:
                        imports_not_at_top = analyzer.find_imports_not_at_top(
                            full_path, source_code
                        )
                        for imp in imports_not_at_top:
                            imp["file_path"] = file_path_str
                        all_imports_not_at_top.extend(imports_not_at_top)

                    if check_duplicates:
                        detector = DuplicateDetector(
                            min_lines=duplicate_min_lines,
                            min_similarity=duplicate_min_similarity,
                            use_semantic=False,
                        )
                        duplicates = detector.find_duplicates_in_file(str(full_path))
                        for group in duplicates:
                            for occ in group["occurrences"]:
                                occ["file_path"] = file_path_str
                        all_duplicates.extend(duplicates)

                    if check_flake8:
                        flake8_result = analyzer.check_flake8(full_path)
                        if not flake8_result["success"]:
                            flake8_result["file_path"] = file_path_str
                            all_flake8_errors.append(flake8_result)

                    if check_mypy:
                        mypy_result = analyzer.check_mypy(full_path, mypy_config)
                        if not mypy_result["success"]:
                            mypy_result["file_path"] = file_path_str
                            all_mypy_errors.append(mypy_result)

                    if check_docstrings:
                        missing_docstrings = analyzer.find_missing_docstrings(
                            full_path, source_code
                        )
                        for d in missing_docstrings:
                            d["file_path"] = file_path_str
                        all_missing_docstrings.extend(missing_docstrings)

                    # Update progress
                    if progress_tracker and files_total > 0:
                        percent = int(((idx + 1) / files_total) * 100)
                        if percent != last_percent:
                            progress_tracker.set_progress(percent)
                            progress_tracker.set_description(
                                f"Analyzing: {idx + 1}/{files_total} ({percent}%)"
                            )
                            last_percent = percent

                results["placeholders"] = all_placeholders
                results["stubs"] = all_stubs
                results["empty_methods"] = all_empty_methods
                results["imports_not_at_top"] = all_imports_not_at_top
                results["duplicates"] = all_duplicates
                results["flake8_errors"] = all_flake8_errors
                results["mypy_errors"] = all_mypy_errors
                results["missing_docstrings"] = all_missing_docstrings

                if check_long_files:
                    results["long_files"] = analyzer.find_long_files(file_records)

            # Create summary
            results["summary"] = {
                "total_placeholders": len(results["placeholders"]),
                "total_stubs": len(results["stubs"]),
                "total_empty_methods": len(results["empty_methods"]),
                "total_imports_not_at_top": len(results["imports_not_at_top"]),
                "total_long_files": len(results["long_files"]),
                "total_duplicate_groups": len(results["duplicates"]),
                "total_duplicate_occurrences": sum(
                    len(g["occurrences"]) for g in results["duplicates"]
                ),
                "total_flake8_errors": sum(
                    e.get("error_count", 0) for e in results["flake8_errors"]
                ),
                "files_with_flake8_errors": len(results["flake8_errors"]),
                "total_mypy_errors": sum(
                    e.get("error_count", 0) for e in results["mypy_errors"]
                ),
                "files_with_mypy_errors": len(results["mypy_errors"]),
                "total_missing_docstrings": len(results["missing_docstrings"]),
                "files_without_docstrings": len(
                    set(
                        d["file_path"]
                        for d in results["missing_docstrings"]
                        if d["type"] == "file"
                    )
                ),
                "classes_without_docstrings": len(
                    [d for d in results["missing_docstrings"] if d["type"] == "class"]
                ),
                "methods_without_docstrings": len(
                    [d for d in results["missing_docstrings"] if d["type"] == "method"]
                ),
                "functions_without_docstrings": len(
                    [d for d in results["missing_docstrings"] if d["type"] == "function"]
                ),
            }

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
