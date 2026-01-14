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
from ..core.constants import DEFAULT_MAX_FILE_LINES
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

            # Resolve project_id: if explicitly provided, use it; otherwise infer from root_dir
            # If project_id is None and we can't infer it, we'll analyze all projects
            proj_id = None
            if project_id:
                # Explicit project_id provided - validate it exists
                proj_id = self._get_project_id(db, root_path, project_id)
                if not proj_id:
                    db.disconnect()
                    return ErrorResult(
                        message="Project not found", code="PROJECT_NOT_FOUND"
                    )
            else:
                # No explicit project_id - try to infer from root_dir
                # If inference fails, proj_id remains None and we analyze all projects
                proj_id = self._get_project_id(db, root_path, None)

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

            if file_path:
                # Analyze specific file
                file_path_obj = self._validate_file_path(file_path, root_path)
                if not file_path_obj.exists():
                    db.disconnect()
                    return ErrorResult(message="File not found", code="FILE_NOT_FOUND")

                # Get absolute path for database lookup
                abs_path = str(file_path_obj.resolve())
                rel_path = str(file_path_obj.relative_to(root_path))

                # Get file_id and mtime
                file_mtime = file_path_obj.stat().st_mtime
                file_id = None
                file_project_id = proj_id

                # Try to find file in database - ONLY in specified project
                if proj_id:
                    file_record = db.get_file_by_path(
                        abs_path, proj_id, include_deleted=False
                    )
                    if file_record:
                        file_id = file_record["id"]
                        file_project_id = proj_id
                        analysis_logger.debug(
                            f"Found file in project: file_id={file_id}, project_id={file_project_id}"
                        )
                    else:
                        # Check if file exists in this project but marked as deleted
                        file_record_deleted = db.get_file_by_path(
                            abs_path, proj_id, include_deleted=True
                        )
                        if file_record_deleted and file_record_deleted.get("deleted"):
                            analysis_logger.warning(
                                f"File found in project {proj_id} but marked as deleted (file_id={file_record_deleted['id']}). "
                                f"File exists on disk at {abs_path}. This indicates data inconsistency."
                            )
                            # File exists on disk but marked as deleted - this is an inconsistency
                            # We can still analyze it, but won't save results
                        else:
                            # File not found in specified project - check if it exists in another project
                            # This is a data inconsistency: file should be in correct project or marked as deleted
                            result = db.execute(
                                "SELECT id, project_id, deleted FROM files WHERE path = ? LIMIT 1",
                                (abs_path,),
                            )
                            data = result.get("data", [])
                            file_in_wrong_project = data[0] if data else None
                            if file_in_wrong_project:
                                wrong_file_id = file_in_wrong_project["id"]
                                wrong_project_id = file_in_wrong_project["project_id"]
                                is_deleted = file_in_wrong_project.get("deleted", 0)

                                analysis_logger.error(
                                    f"Data inconsistency detected: file exists on disk at {abs_path} "
                                    f"but is registered in project {wrong_project_id} (not {proj_id}). "
                                    f"File ID: {wrong_file_id}, deleted={is_deleted}. "
                                    f"Marking as deleted and clearing all related data."
                                )

                                # Clear all related data for this file
                                try:
                                    db.clear_file_data(wrong_file_id)
                                    analysis_logger.info(
                                        f"Cleared all related data for file_id={wrong_file_id}"
                                    )

                                    # Mark file as deleted in wrong project
                                    db.execute(
                                        """
                                        UPDATE files 
                                        SET deleted = 1, updated_at = julianday('now')
                                        WHERE id = ?
                                        """,
                                        (wrong_file_id,),
                                    )
                                    analysis_logger.info(
                                        f"Marked file_id={wrong_file_id} as deleted in project {wrong_project_id}"
                                    )

                                    # Try to add file to correct project if it exists on disk
                                    if file_path_obj.exists() and proj_id:
                                        try:
                                            # Check if file is within the correct project's root
                                            try:
                                                file_path_obj.relative_to(root_path)
                                                # File is within project root - add it to correct project
                                                from code_analysis.core.project_resolution import (
                                                    normalize_root_dir,
                                                )

                                                normalized_root = str(
                                                    normalize_root_dir(root_path)
                                                )
                                                dataset_id = db.get_dataset_id(
                                                    proj_id, normalized_root
                                                )
                                                if not dataset_id:
                                                    from .base_mcp_command import (
                                                        BaseMCPCommand,
                                                    )

                                                    dataset_id = BaseMCPCommand._get_or_create_dataset(
                                                        db, proj_id, normalized_root
                                                    )

                                                # Read file metadata
                                                text = file_path_obj.read_text(
                                                    encoding="utf-8", errors="ignore"
                                                )
                                                lines = text.count("\n") + (
                                                    1 if text else 0
                                                )
                                                stripped = text.lstrip()
                                                has_docstring = stripped.startswith(
                                                    '"""'
                                                ) or stripped.startswith("'''")

                                                # Add file to correct project
                                                new_file_id = db.add_file(
                                                    path=abs_path,
                                                    lines=lines,
                                                    last_modified=file_mtime,
                                                    has_docstring=has_docstring,
                                                    project_id=proj_id,
                                                    dataset_id=dataset_id,
                                                )
                                                file_id = new_file_id
                                                file_project_id = proj_id
                                                analysis_logger.info(
                                                    f"Added file to correct project {proj_id}: file_id={new_file_id}"
                                                )
                                            except ValueError:
                                                # File is not within project root - this is expected for nested projects
                                                analysis_logger.info(
                                                    f"File {abs_path} is not within project root {root_path}, skipping addition to project {proj_id}"
                                                )
                                        except Exception as e:
                                            logger.error(
                                                f"Failed to add file to correct project: {e}",
                                                exc_info=True,
                                            )
                                            analysis_logger.error(
                                                f"Failed to add file to correct project: {e}",
                                                exc_info=True,
                                            )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to clear data and mark file as deleted: {e}",
                                        exc_info=True,
                                    )
                                    analysis_logger.error(
                                        f"Failed to clear data and mark file as deleted: {e}",
                                        exc_info=True,
                                    )
                            else:
                                # File not in database at all - this is normal for unindexed files
                                analysis_logger.info(
                                    f"File not found in project {proj_id} database (may be unindexed): {abs_path}"
                                )
                else:
                    # No project_id specified - can't look up in database
                    analysis_logger.info(
                        f"No project_id specified, cannot look up file in database: {abs_path}"
                    )

                # Check if analysis is up-to-date
                if file_id and file_project_id:
                    if db.is_analysis_up_to_date(file_id, file_mtime):
                        # Get cached results
                        cached = db.get_comprehensive_analysis_results(
                            file_id, file_mtime
                        )
                        if cached:
                            db.disconnect()
                            if progress_tracker:
                                progress_tracker.set_status("completed")
                                progress_tracker.set_description(
                                    "Analysis completed (cached)"
                                )
                                progress_tracker.set_progress(100)
                            analysis_logger.info(
                                f"Using cached analysis results for {rel_path}"
                            )
                            # Return cached results with summary including statistics
                            cached_summary = cached["summary"].copy()
                            cached_summary["files_analyzed"] = 0
                            cached_summary["files_skipped"] = 1
                            cached_summary["files_total"] = 1
                            return SuccessResult(
                                data={
                                    **cached["results"],
                                    "summary": cached_summary,
                                }
                            )

                # File needs analysis
                files_analyzed = 1
                files_total = 1

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

                # Save results to database if file_id is available
                # Only save if file was found in the correct project (file_project_id == proj_id)
                if (
                    file_id
                    and file_project_id
                    and (proj_id is None or file_project_id == proj_id)
                ):
                    try:
                        analysis_logger.info(
                            f"Saving results for file_id={file_id}, project_id={file_project_id}, mtime={file_mtime}"
                        )
                        file_summary = {
                            "total_placeholders": len(results["placeholders"]),
                            "total_stubs": len(results["stubs"]),
                            "total_empty_methods": len(results["empty_methods"]),
                            "total_imports_not_at_top": len(
                                results["imports_not_at_top"]
                            ),
                            "total_duplicate_groups": len(results["duplicates"]),
                            "total_duplicate_occurrences": sum(
                                len(g["occurrences"]) for g in results["duplicates"]
                            ),
                            "total_flake8_errors": sum(
                                e.get("error_count", 0)
                                for e in results.get("flake8_errors", [])
                            ),
                            "files_with_flake8_errors": len(
                                results.get("flake8_errors", [])
                            ),
                            "total_mypy_errors": sum(
                                e.get("error_count", 0)
                                for e in results.get("mypy_errors", [])
                            ),
                            "files_with_mypy_errors": len(
                                results.get("mypy_errors", [])
                            ),
                            "total_missing_docstrings": len(
                                results["missing_docstrings"]
                            ),
                        }
                        db.save_comprehensive_analysis_results(
                            file_id=file_id,
                            project_id=file_project_id,
                            file_mtime=file_mtime,
                            results=results,
                            summary=file_summary,
                        )
                        analysis_logger.info(f"Saved analysis results for {rel_path}")
                    except Exception as e:
                        logger.error(
                            f"Failed to save analysis results for {rel_path}: {e}",
                            exc_info=True,
                        )
                        analysis_logger.error(
                            f"Failed to save analysis results for {rel_path}: {e}",
                            exc_info=True,
                        )
                else:
                    if (
                        file_id
                        and file_project_id
                        and proj_id
                        and file_project_id != proj_id
                    ):
                        analysis_logger.error(
                            f"Data inconsistency detected: file_id={file_id} belongs to project {file_project_id}, "
                            f"but analysis was requested for project {proj_id}. Results will not be saved."
                        )
                    else:
                        analysis_logger.warning(
                            f"Cannot save results: file_id={file_id}, file_project_id={file_project_id}, proj_id={proj_id}"
                        )

            else:
                # Analyze multiple files
                if proj_id:
                    # Analyze all files in specific project
                    project_files = db.get_project_files(proj_id, include_deleted=False)
                    files = [
                        {"id": f["id"], "path": f["path"], "lines": f.get("lines", 0)}
                        for f in project_files
                    ]
                    analysis_logger.info(
                        f"Starting comprehensive analysis for project {proj_id}: {len(files)} files to analyze"
                    )
                else:
                    # Analyze all files in ALL projects
                    result = db.execute(
                        "SELECT id, path, lines, project_id FROM files WHERE deleted = 0"
                    )
                    files = result.get("data", [])
                    analysis_logger.info(
                        f"Starting comprehensive analysis for all projects: {len(files)} files to analyze"
                    )

                files_total = len(files)
                if progress_tracker:
                    if proj_id:
                        progress_tracker.set_description(
                            f"Analyzing {files_total} files in project..."
                        )
                    else:
                        progress_tracker.set_description(
                            f"Analyzing {files_total} files in all projects..."
                        )
                    progress_tracker.set_progress(0)
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
                files_analyzed = 0
                files_skipped = 0
                for idx, file_record in enumerate(files):
                    file_path_str = file_record["path"]
                    file_id = file_record["id"]

                    # Resolve full path
                    if Path(file_path_str).is_absolute():
                        full_path = Path(file_path_str)
                    else:
                        full_path = root_path / file_path_str

                    if not full_path.exists() or not full_path.is_file():
                        logger.debug(f"Skipping non-existent file: {file_path_str}")
                        continue

                    # Get file modification time from disk
                    try:
                        file_mtime = full_path.stat().st_mtime
                    except Exception as e:
                        logger.warning(f"Failed to get mtime for {file_path_str}: {e}")
                        continue

                    # Check if analysis is up-to-date
                    if db.is_analysis_up_to_date(file_id, file_mtime):
                        files_skipped += 1
                        logger.debug(f"Skipping unchanged file: {file_path_str}")
                        analysis_logger.debug(
                            f"Skipping unchanged file: {file_path_str}"
                        )
                        # Still add to file_records for long_files check
                        file_records.append(
                            {
                                "path": file_path_str,
                                "lines": file_record.get("lines", 0),
                            }
                        )
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
                    files_analyzed += 1
                    logger.info(
                        f"Analyzing file {idx + 1}/{files_total}: {file_path_str}"
                    )
                    analysis_logger.info(
                        f"Analyzing file {idx + 1}/{files_total}: {file_path_str}"
                    )

                    # Initialize file-specific results
                    file_results: Dict[str, Any] = {
                        "placeholders": [],
                        "stubs": [],
                        "empty_methods": [],
                        "imports_not_at_top": [],
                        "duplicates": [],
                        "flake8_errors": [],
                        "mypy_errors": [],
                        "missing_docstrings": [],
                    }

                    # Run checks
                    if check_placeholders:
                        placeholders = analyzer.find_placeholders(
                            full_path, source_code
                        )
                        for p in placeholders:
                            p["file_path"] = file_path_str
                        file_results["placeholders"] = placeholders
                        all_placeholders.extend(placeholders)

                    if check_stubs:
                        stubs = analyzer.find_stubs(full_path, source_code)
                        for s in stubs:
                            s["file_path"] = file_path_str
                        file_results["stubs"] = stubs
                        all_stubs.extend(stubs)

                    if check_empty_methods:
                        empty_methods = analyzer.find_empty_methods(
                            full_path, source_code
                        )
                        for m in empty_methods:
                            m["file_path"] = file_path_str
                        file_results["empty_methods"] = empty_methods
                        all_empty_methods.extend(empty_methods)

                    if check_imports:
                        imports_not_at_top = analyzer.find_imports_not_at_top(
                            full_path, source_code
                        )
                        for imp in imports_not_at_top:
                            imp["file_path"] = file_path_str
                        file_results["imports_not_at_top"] = imports_not_at_top
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
                        file_results["duplicates"] = duplicates
                        all_duplicates.extend(duplicates)

                    if check_flake8:
                        flake8_result = analyzer.check_flake8(full_path)
                        if not flake8_result["success"]:
                            flake8_result["file_path"] = file_path_str
                            file_results["flake8_errors"] = [flake8_result]
                            all_flake8_errors.append(flake8_result)

                    if check_mypy:
                        mypy_result = analyzer.check_mypy(full_path, mypy_config)
                        if not mypy_result["success"]:
                            mypy_result["file_path"] = file_path_str
                            file_results["mypy_errors"] = [mypy_result]
                            all_mypy_errors.append(mypy_result)

                    if check_docstrings:
                        missing_docstrings = analyzer.find_missing_docstrings(
                            full_path, source_code
                        )
                        for d in missing_docstrings:
                            d["file_path"] = file_path_str
                        file_results["missing_docstrings"] = missing_docstrings
                        all_missing_docstrings.extend(missing_docstrings)

                    # Create file-specific summary
                    file_summary = {
                        "total_placeholders": len(file_results["placeholders"]),
                        "total_stubs": len(file_results["stubs"]),
                        "total_empty_methods": len(file_results["empty_methods"]),
                        "total_imports_not_at_top": len(
                            file_results["imports_not_at_top"]
                        ),
                        "total_duplicate_groups": len(file_results["duplicates"]),
                        "total_duplicate_occurrences": sum(
                            len(g["occurrences"]) for g in file_results["duplicates"]
                        ),
                        "total_flake8_errors": sum(
                            e.get("error_count", 0)
                            for e in file_results.get("flake8_errors", [])
                        ),
                        "files_with_flake8_errors": len(
                            file_results.get("flake8_errors", [])
                        ),
                        "total_mypy_errors": sum(
                            e.get("error_count", 0)
                            for e in file_results.get("mypy_errors", [])
                        ),
                        "files_with_mypy_errors": len(
                            file_results.get("mypy_errors", [])
                        ),
                        "total_missing_docstrings": len(
                            file_results["missing_docstrings"]
                        ),
                    }

                    # Save results to database
                    # Get project_id: use proj_id if set, otherwise from file_record
                    file_project_id = proj_id or file_record.get("project_id")
                    if file_project_id:
                        try:
                            analysis_logger.info(
                                f"Saving results for file_id={file_id}, project_id={file_project_id}, mtime={file_mtime}, file={file_path_str}"
                            )
                            db.save_comprehensive_analysis_results(
                                file_id=file_id,
                                project_id=file_project_id,
                                file_mtime=file_mtime,
                                results=file_results,
                                summary=file_summary,
                            )
                            analysis_logger.info(
                                f"Saved analysis results for {file_path_str}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to save analysis results for {file_path_str}: {e}",
                                exc_info=True,
                            )
                            analysis_logger.error(
                                f"Failed to save analysis results for {file_path_str}: {e}",
                                exc_info=True,
                            )
                    else:
                        logger.warning(
                            f"Cannot save results for {file_path_str}: project_id not available (proj_id={proj_id}, file_record.project_id={file_record.get('project_id')})"
                        )
                        analysis_logger.warning(
                            f"Cannot save results for {file_path_str}: project_id not available"
                        )

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

                # Log statistics
                analysis_logger.info(
                    f"Analysis complete: {files_analyzed} files analyzed, {files_skipped} files skipped (unchanged)"
                )

            # Create summary
            summary_data = {
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
                    [
                        d
                        for d in results["missing_docstrings"]
                        if d["type"] == "function"
                    ]
                ),
            }

            # Add incremental analysis statistics
            summary_data["files_analyzed"] = files_analyzed
            summary_data["files_skipped"] = files_skipped
            summary_data["files_total"] = files_total

            results["summary"] = summary_data

            db.disconnect()

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

    @classmethod
    def metadata(cls: type["ComprehensiveAnalysisMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The comprehensive_analysis command performs comprehensive code quality analysis "
                "combining multiple analysis types in a single operation. This is a long-running "
                "command executed via queue and provides detailed code quality metrics.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id:\n"
                "   - If project_id parameter provided, validates it exists\n"
                "   - If not provided, tries to infer from root_dir\n"
                "   - If cannot infer, project_id remains None (analyze all projects)\n"
                "4. Sets up dedicated log file (logs/comprehensive_analysis.log)\n"
                "5. Initializes ComprehensiveAnalyzer and DuplicateDetector\n"
                "6. If file_path provided:\n"
                "   - Analyzes single file with all enabled checks\n"
                "7. If file_path not provided:\n"
                "   - If project_id is set: Analyzes all files in that project\n"
                "   - If project_id is None: Analyzes ALL files in ALL projects\n"
                "   - Processes files with progress tracking\n"
                "   - Runs all enabled checks for each file\n"
                "8. Aggregates results and creates summary statistics\n"
                "9. Saves results to database (comprehensive_analysis_results table)\n"
                "10. Returns comprehensive analysis results\n\n"
                "Incremental Analysis:\n"
                "- Before analyzing each file, checks file modification time (mtime)\n"
                "- Compares mtime with stored analysis results in database\n"
                "- Skips files where mtime matches (analysis is up-to-date)\n"
                "- Only analyzes changed files (mtime differs)\n"
                "- For single file mode: returns cached results if file unchanged\n\n"
                "Analysis Types:\n"
                "- Placeholders: Finds TODO, FIXME, XXX, HACK, NOTE comments\n"
                "- Stubs: Finds functions/methods with pass, ellipsis, NotImplementedError\n"
                "- Empty methods: Finds methods without body (excluding abstract methods)\n"
                "- Imports not at top: Finds imports after non-import statements\n"
                "- Long files: Finds files exceeding max_lines threshold\n"
                "- Duplicates: Finds code duplicates (structural and semantic)\n"
                "- Flake8: Runs flake8 linter and reports errors\n"
                "- Mypy: Runs mypy type checker and reports errors\n"
                "- Missing docstrings: Finds files/classes/methods/functions without docstrings\n\n"
                "Use cases:\n"
                "- Complete code quality audit\n"
                "- Identify code quality issues before refactoring\n"
                "- Monitor code quality metrics\n"
                "- Find technical debt indicators\n"
                "- Generate code quality reports\n\n"
                "Important notes:\n"
                "- This is a long-running command (use_queue=True)\n"
                "- When file_path not provided:\n"
                "  * If project_id is set: analyzes all files in that project\n"
                "  * If project_id is None: analyzes ALL files in ALL projects\n"
                "- Progress is tracked and logged to logs/comprehensive_analysis.log\n"
                "- Each check can be enabled/disabled via boolean parameters\n"
                "- Results include summary statistics for all analysis types\n"
                "- Results are saved to database (comprehensive_analysis_results table)\n"
                "- Incremental analysis: only analyzes files that have changed since last analysis\n"
                "- Files with unchanged mtime are skipped (analysis is up-to-date)\n"
                "- Single file mode: returns cached results if file unchanged"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db file."
                    ),
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": (
                        "Optional path to specific file to analyze. If provided, only analyzes this file. "
                        "If omitted, analyzes files based on project_id parameter (see project_id description)."
                    ),
                    "type": "string",
                    "required": False,
                },
                "max_lines": {
                    "description": (
                        "Maximum lines threshold for long files check. Default is 400. "
                        "Files exceeding this threshold are reported as long files."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 400,
                },
                "check_placeholders": {
                    "description": (
                        "Check for placeholders (TODO, FIXME, XXX, HACK, NOTE). Default is True."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "check_stubs": {
                    "description": (
                        "Check for stub functions/methods (pass, ellipsis, NotImplementedError). "
                        "Default is True."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "check_empty_methods": {
                    "description": (
                        "Check for empty methods (excluding abstract methods). Default is True."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "check_imports": {
                    "description": (
                        "Check for imports not at top of file. Default is True."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "check_long_files": {
                    "description": (
                        "Check for long files (exceeding max_lines). Default is True."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "check_duplicates": {
                    "description": ("Check for code duplicates. Default is True."),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "check_flake8": {
                    "description": ("Check code with flake8 linter. Default is True."),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "check_mypy": {
                    "description": (
                        "Check code with mypy type checker. Default is True."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "check_docstrings": {
                    "description": (
                        "Check for missing docstrings (files, classes, methods, functions). "
                        "Default is True."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "duplicate_min_lines": {
                    "description": (
                        "Minimum lines for duplicate detection. Default is 5."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 5,
                },
                "duplicate_min_similarity": {
                    "description": (
                        "Minimum similarity for duplicates (0.0-1.0). Default is 0.8."
                    ),
                    "type": "number",
                    "required": False,
                    "default": 0.8,
                },
                "mypy_config_file": {
                    "description": (
                        "Optional path to mypy config file. If provided, uses this config for mypy checks."
                    ),
                    "type": "string",
                    "required": False,
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. "
                        "If provided: analyzes all files in that project (when file_path not provided). "
                        "If omitted: tries to infer from root_dir. "
                        "If cannot infer: analyzes all files in all projects (when file_path not provided)."
                    ),
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "Run full comprehensive analysis on all files in all projects",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        # project_id not provided - analyzes all projects
                    },
                    "explanation": (
                        "Runs all checks on all files in all projects. This is a long-running operation. "
                        "Use queue_get_job_status to check progress."
                    ),
                },
                {
                    "description": "Analyze all files in specific project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                    },
                    "explanation": (
                        "Runs all checks on all files in the specified project only. "
                        "Faster than analyzing all projects."
                    ),
                },
                {
                    "description": "Analyze specific file with all checks",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Runs all checks on src/main.py file only. Faster than project-wide analysis."
                    ),
                },
                {
                    "description": "Run only specific checks",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "check_placeholders": True,
                        "check_stubs": True,
                        "check_duplicates": False,
                        "check_flake8": False,
                        "check_mypy": False,
                    },
                    "explanation": (
                        "Runs only placeholder and stub checks, skipping duplicates and linting."
                    ),
                },
                {
                    "description": "Check with custom duplicate settings",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "duplicate_min_lines": 10,
                        "duplicate_min_similarity": 0.9,
                    },
                    "explanation": (
                        "Finds duplicates with minimum 10 lines and 90% similarity."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "FILE_NOT_FOUND": {
                    "description": "File not found",
                    "example": "file_path='src/main.py' but file doesn't exist",
                    "solution": "Verify file path is correct and file exists.",
                },
                "COMPREHENSIVE_ANALYSIS_ERROR": {
                    "description": "General error during comprehensive analysis",
                    "example": "Database error, analysis failure, or tool execution error",
                    "solution": (
                        "Check database integrity, verify file paths, ensure analysis tools "
                        "(flake8, mypy) are installed. Check logs/comprehensive_analysis.log for details."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "placeholders": "List of placeholder comments (TODO, FIXME, etc.)",
                        "stubs": "List of stub functions/methods",
                        "empty_methods": "List of empty methods",
                        "imports_not_at_top": "List of imports not at top of file",
                        "long_files": "List of files exceeding max_lines",
                        "duplicates": "List of duplicate code groups",
                        "flake8_errors": "List of flake8 linting errors",
                        "mypy_errors": "List of mypy type checking errors",
                        "missing_docstrings": "List of missing docstrings (files, classes, methods, functions)",
                        "summary": (
                            "Summary statistics dictionary with:\n"
                            "- total_placeholders, total_stubs, total_empty_methods\n"
                            "- total_imports_not_at_top, total_long_files\n"
                            "- total_duplicate_groups, total_duplicate_occurrences\n"
                            "- total_flake8_errors, files_with_flake8_errors\n"
                            "- total_mypy_errors, files_with_mypy_errors\n"
                            "- total_missing_docstrings, files_without_docstrings\n"
                            "- classes_without_docstrings, methods_without_docstrings\n"
                            "- functions_without_docstrings"
                        ),
                    },
                    "example": {
                        "placeholders": [
                            {
                                "file_path": "src/main.py",
                                "line": 42,
                                "type": "TODO",
                                "text": "TODO: refactor",
                            },
                        ],
                        "stubs": [
                            {
                                "file_path": "src/utils.py",
                                "line": 10,
                                "name": "stub_function",
                                "type": "function",
                            },
                        ],
                        "summary": {
                            "total_placeholders": 1,
                            "total_stubs": 1,
                            "total_empty_methods": 0,
                            "total_long_files": 0,
                            "total_duplicate_groups": 0,
                            "total_flake8_errors": 0,
                            "total_mypy_errors": 0,
                        },
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, FILE_NOT_FOUND, COMPREHENSIVE_ANALYSIS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use file_path parameter for faster analysis of specific files",
                "Use project_id parameter to analyze specific project instead of all projects",
                "Disable checks you don't need to improve performance",
                "Use queue_get_job_status to monitor progress for project-wide analysis",
                "Check logs/comprehensive_analysis.log for detailed analysis logs",
                "Review summary statistics first, then drill down into specific issues",
                "Run this command regularly to track code quality over time",
                "Use custom duplicate settings to focus on significant duplicates",
                "Results are automatically saved to database - incremental analysis improves performance",
                "Only changed files are analyzed - unchanged files are skipped automatically",
            ],
            "data_persistence": {
                "results_saved_to_database": True,
                "description": (
                    "Results of comprehensive_analysis are saved to the database in the "
                    "comprehensive_analysis_results table. Each file's analysis results are stored "
                    "with the file's modification time (mtime) to enable incremental analysis."
                ),
                "what_is_saved": (
                    "For each analyzed file:\n"
                    "- File ID and project ID\n"
                    "- File modification time (mtime) at analysis\n"
                    "- Complete analysis results (JSON)\n"
                    "- Summary statistics (JSON)\n"
                    "- Timestamp of analysis\n"
                    "Results are stored in comprehensive_analysis_results table with UNIQUE(file_id, file_mtime) constraint."
                ),
                "incremental_analysis": (
                    "Before analyzing a file, the command:\n"
                    "1. Gets file modification time (mtime) from disk\n"
                    "2. Checks if analysis results exist in database for this file_id and mtime\n"
                    "3. If mtime matches (within 0.1s tolerance): skips analysis, uses cached results\n"
                    "4. If mtime differs: performs analysis and saves new results\n"
                    "This ensures only changed files are analyzed, improving performance."
                ),
                "what_is_returned": (
                    "Complete analysis results including:\n"
                    "- All findings (placeholders, stubs, empty methods, etc.)\n"
                    "- Summary statistics\n"
                    "- All errors and warnings\n"
                    "All data is returned in the SuccessResult.data dictionary.\n"
                    "For single file mode with unchanged file: returns cached results from database."
                ),
            },
        }
