"""
MCP command wrapper for code index update.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..core.constants import (
    DATA_DIR_NAME,
    DEFAULT_IGNORE_PATTERNS,
    DEFAULT_MAX_FILE_LINES,
    LOGS_DIR_NAME,
)
from .base_mcp_command import BaseMCPCommand
from .update_indexes_analyzer import analyze_file
from .update_indexes_metadata import get_metadata as get_update_indexes_metadata
from .update_indexes_metadata import get_schema as get_update_indexes_schema

logger = logging.getLogger(__name__)


class UpdateIndexesMCPCommand(BaseMCPCommand):
    """Update code indexes by analyzing project files and adding them to database.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "update_indexes"
    version = "1.0.0"
    descr = "Update code indexes by analyzing project files and adding them to database"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True  # This can be long-running, use queue

    @classmethod
    def get_schema(cls: type["UpdateIndexesMCPCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters (MCP Proxy validation)."""
        return get_update_indexes_schema()

    def _analyze_file(
        self: "UpdateIndexesMCPCommand",
        database: Any,
        file_path: Path,
        project_id: str,
        root_path: Path,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Backward-compatible wrapper for single-file analysis.

        Some database workflows call ``UpdateIndexesMCPCommand._analyze_file`` directly.
        This method preserves that public surface and delegates to the current
        implementation in ``update_indexes_analyzer.analyze_file``.

        Args:
            database: Open database client.
            file_path: Absolute file path to analyze.
            project_id: Project identifier.
            root_path: Project root path.
            force: Force re-analysis even if mtime is unchanged.

        Returns:
            Per-file analysis result dictionary.
        """
        return analyze_file(
            database=database,
            file_path=file_path,
            project_id=project_id,
            root_path=root_path,
            force=force,
        )

    async def execute(
        self: "UpdateIndexesMCPCommand",
        project_id: str,
        max_lines: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute code index update.

        Notes:
            Uses project_id to resolve project root from the shared database.
            If the database is detected as corrupted, this command will create a
            filesystem backup, write a persistent corruption marker, stop workers,
            and return an error. The project is then in "safe mode" until explicit
            repair/restore.

        Args:
            self: Command instance.
            project_id: Project UUID (from create_project or list_projects). Required.
            max_lines: Maximum lines per file threshold (for reporting).
                If None, uses DEFAULT_MAX_FILE_LINES from constants.
            **kwargs: Extra parameters (may include 'context' with ProgressTracker).

        Returns:
            SuccessResult with update results or ErrorResult on failure.
        """
        if max_lines is None:
            max_lines = DEFAULT_MAX_FILE_LINES

        from ..core.progress_tracker import get_progress_tracker_from_context

        progress_tracker = get_progress_tracker_from_context(
            kwargs.get("context") or {}
        )

        try:
            if progress_tracker:
                progress_tracker.set_status("running")
                progress_tracker.set_description("Resolving project...")
                progress_tracker.set_progress(0)

            database = self._open_database_from_config(auto_analyze=False)
            try:
                project = database.get_project(project_id)
                if not project or not project.root_path:
                    return ErrorResult(
                        message=f"Project not found: {project_id}",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )
                root_path = Path(project.root_path)
                if not root_path.exists() or not root_path.is_dir():
                    return ErrorResult(
                        message=(
                            f"Project root path does not exist or is not a directory: {root_path}"
                        ),
                        code="PROJECT_ROOT_NOT_FOUND",
                        details={"project_id": project_id, "root_path": str(root_path)},
                    )

                if progress_tracker:
                    progress_tracker.set_description("Scanning for Python files...")
                    progress_tracker.set_progress(0)

                python_files: list[Path] = []
                # Build ignore set from constants
                ignore_dirs = DEFAULT_IGNORE_PATTERNS | {DATA_DIR_NAME, LOGS_DIR_NAME}
                for walk_root, dirs, files in os.walk(root_path):
                    dirs[:] = [
                        d
                        for d in dirs
                        if not d.startswith(".") and d not in ignore_dirs
                    ]
                    for file in files:
                        if file.endswith(".py"):
                            python_files.append(Path(walk_root) / file)

                files_total = len(python_files)
                trigger = kwargs.get("trigger") or "manual"
                # Log update_indexes start for correlation with status snapshots (see docs/WORKER_AND_DB_STATUS_ANALYSIS.md)
                logger.info(
                    "[update_indexes START] project_id=%s files_total=%s root_path=%s trigger=%s",
                    project_id,
                    files_total,
                    str(root_path),
                    trigger,
                )
                if progress_tracker:
                    progress_tracker.set_description(
                        f"Processing {files_total} Python file(s) for indexing..."
                    )
                    progress_tracker.set_progress(0)

                if files_total == 0:
                    if progress_tracker:
                        progress_tracker.set_progress(100)
                        progress_tracker.set_description(
                            "No Python files found; nothing to index"
                        )
                        progress_tracker.set_status("completed")
                    return SuccessResult(
                        data={
                            "project_id": project_id,
                            "root_path": str(root_path),
                            "files_processed": 0,
                            "files_total": 0,
                            "files_discovered": 0,
                            "errors": 0,
                            "syntax_errors": 0,
                            "classes": 0,
                            "functions": 0,
                            "methods": 0,
                            "imports": 0,
                            "db_repaired": False,
                            "db_backup_paths": [],
                            "message": "No Python files found",
                        }
                    )

                def process_files() -> list[Dict[str, Any]]:
                    """Process files and update progress.

                    Returns:
                        List of per-file results.
                    """
                    results: list[Dict[str, Any]] = []
                    error_samples: list[Dict[str, str]] = []
                    last_percent = -1

                    for idx, file_path in enumerate(python_files):

                        def make_heartbeat_cb(
                            i: int, total: int
                        ) -> Callable[[str], None]:
                            def cb(phase: str) -> None:
                                if progress_tracker:
                                    pct = int((i + 1) / total * 100)
                                    progress_tracker.set_description(
                                        f"Indexing: {i + 1}/{total} ({pct}%) — {phase}"
                                    )

                            return cb

                        progress_cb = make_heartbeat_cb(idx, files_total)
                        result = analyze_file(
                            database,
                            file_path,
                            project_id,
                            root_path,
                            progress_callback=progress_cb,
                        )
                        results.append(result)

                        if result.get("status") == "error" and len(error_samples) < 5:
                            error_samples.append(
                                {
                                    "file": result.get("file", str(file_path)),
                                    "error": result.get("error", "Unknown error"),
                                    "error_type": result.get("error_type", "Unknown"),
                                }
                            )

                        if progress_tracker:
                            percent = int(((idx + 1) / files_total) * 100)
                            if percent != last_percent:
                                progress_tracker.set_progress(percent)
                                progress_tracker.set_description(
                                    f"Indexing: {idx + 1}/{files_total} ({percent}%)"
                                )
                                last_percent = percent

                        if (idx + 1) % 100 == 0:
                            logger.info(f"Processed {idx + 1}/{files_total} files...")

                    if error_samples:
                        logger.warning(f"Sample errors (first {len(error_samples)}):")
                        for sample in error_samples:
                            logger.warning(
                                f"  {sample['file']}: {sample['error_type']} - {sample['error']}"
                            )

                    return results

                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(None, process_files)

                total = len(results)
                successful = sum(1 for r in results if r.get("status") == "success")
                errors = sum(1 for r in results if r.get("status") == "error")
                syntax_errors = sum(
                    1 for r in results if r.get("status") == "syntax_error"
                )
                total_classes = sum(r.get("classes", 0) for r in results)
                total_functions = sum(r.get("functions", 0) for r in results)
                total_methods = sum(r.get("methods", 0) for r in results)
                total_imports = sum(r.get("imports", 0) for r in results)

                error_details = [
                    {
                        "file": r.get("file", ""),
                        "error": r.get("error", "Unknown"),
                        "error_type": r.get("error_type", "Unknown"),
                    }
                    for r in results
                    if r.get("status") == "error"
                ]

                if progress_tracker:
                    progress_tracker.set_progress(100)
                    progress_tracker.set_description("Indexing completed")
                    progress_tracker.set_status("completed")

                # Log update_indexes end for correlation with status snapshots
                logger.info(
                    "[update_indexes END] project_id=%s files_processed=%s files_total=%s errors=%s trigger=%s",
                    project_id,
                    successful,
                    total,
                    errors,
                    trigger,
                )

                data: Dict[str, Any] = {
                    "project_id": project_id,
                    "root_path": str(root_path),
                    "files_processed": successful,
                    "files_total": total,
                    "files_discovered": files_total,
                    "errors": errors,
                    "syntax_errors": syntax_errors,
                    "classes": total_classes,
                    "functions": total_functions,
                    "methods": total_methods,
                    "imports": total_imports,
                    "db_repaired": False,
                    "db_backup_paths": [],
                    "workers_restarted": {},
                    "message": (
                        f"Indexes updated: {successful}/{total} files processed, "
                        f"{errors} errors, {syntax_errors} syntax errors"
                    ),
                }
                if error_details:
                    data["error_details"] = error_details

                return SuccessResult(data=data)
            finally:
                database.disconnect()

        except Exception as e:
            if progress_tracker:
                progress_tracker.set_status("failed")
            return self._handle_error(e, "INDEX_UPDATE_ERROR", "update_indexes")

    @classmethod
    def metadata(cls: type["UpdateIndexesMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_update_indexes_metadata(cls)
