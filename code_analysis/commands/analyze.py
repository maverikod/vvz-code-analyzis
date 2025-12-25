"""
Analyze command implementation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import multiprocessing
import os
import time
from pathlib import Path
from typing import Dict, Any, Optional

from ..core import CodeAnalyzer, CodeDatabase, IssueDetector
from ..core.progress_tracker import ProgressTracker
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.svo_client_manager import SVOClientManager
    from ..core.faiss_manager import FaissIndexManager

logger = logging.getLogger(__name__)


class AnalyzeCommand:
    """Command for analyzing Python projects."""

    def __init__(
        self,
        database: CodeDatabase,
        project_id: str,
        root_path: str,
        max_lines: int = 400,
        force: bool = False,
        svo_client_manager: Optional["SVOClientManager"] = None,
        faiss_manager: Optional["FaissIndexManager"] = None,
        progress_tracker: Optional[ProgressTracker] = None,
    ):
        """
        Initialize analyze command.

        Args:
            database: Database instance
            project_id: Project UUID
            root_path: Root directory path
            max_lines: Maximum lines per file
            force: Force re-analysis
            svo_client_manager: SVO client manager for chunking and embedding
            faiss_manager: FAISS index manager for vector storage
            progress_tracker: Progress tracker for updating job progress
        """
        self.database = database
        self.project_id = project_id
        self.root_path = Path(root_path).resolve()
        self.max_lines = max_lines
        self.force = force
        self.progress_tracker = progress_tracker

        # Initialize analyzer
        output_dir = self.root_path / "code_analysis"
        self.analyzer = CodeAnalyzer(
            str(self.root_path),
            str(output_dir),
            max_lines,
            database=self.database,
            svo_client_manager=svo_client_manager,
            faiss_manager=faiss_manager,
        )
        self.issue_detector = IssueDetector(
            self.analyzer.issues, self.root_path, database=self.database
        )
        self.analyzer.issue_detector = self.issue_detector

    async def execute(self) -> Dict[str, Any]:
        """
        Execute project analysis.

        Returns:
            Dictionary with analysis results
        """

        def _should_analyze(file_path: Path) -> bool:
            if self.force or not self.database:
                return True
            file_mtime = file_path.stat().st_mtime
            file_rec = self.database.get_file_by_path(str(file_path), self.project_id)
            if not file_rec:
                return True  # new file
            db_mtime = file_rec.get("last_modified")
            if db_mtime is None:
                return True
            # Re-run if mtime differs (not strictly newer, DB might be modified)
            return file_mtime != db_mtime

        if self.progress_tracker:
            self.progress_tracker.set_progress(0)
            self.progress_tracker.set_description("Starting project analysis...")
            self.progress_tracker.log(f"Analyzing project: {self.root_path}")

        logger.info(f"Analyzing project: {self.root_path}")

        # Remove files from database that no longer exist on disk
        # This is done ALWAYS before analysis, regardless of force flag
        if self.progress_tracker:
            self.progress_tracker.set_progress(5)
            self.progress_tracker.set_description("Checking for missing files...")
            self.progress_tracker.log(
                f"Checking for missing files in project: {self.project_id}"
            )

        logger.info(f"Checking for missing files in project: {self.project_id}")
        removal_result = await self.database.remove_missing_files(
            self.project_id, self.root_path
        )
        if removal_result["removed_count"] > 0:
            msg = (
                f"Removed {removal_result['removed_count']} missing files: "
                f"{', '.join(removal_result['removed_files'][:5])}"
                + (
                    f" and {len(removal_result['removed_files']) - 5} more"
                    if len(removal_result["removed_files"]) > 5
                    else ""
                )
            )
            logger.info(msg)
            if self.progress_tracker:
                self.progress_tracker.log(msg)

        # Collect all Python files first to calculate progress
        python_files = []
        for root, dirs, files in os.walk(self.root_path):
            # Skip certain directories
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in ["__pycache__", "node_modules", ".venv", "venv"]
            ]

            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    python_files.append(file_path)

        total_files = len(python_files)
        if self.progress_tracker:
            self.progress_tracker.set_progress(10)
            self.progress_tracker.set_description(
                f"Found {total_files} Python files. Starting analysis..."
            )
            self.progress_tracker.log(f"Found {total_files} Python files to analyze")

        # Analyze files with progress updates
        analyzed_count = 0
        for idx, file_path in enumerate(python_files):
            logger.info(
                f"📄 Analyzing file {analyzed_count + 1}/{total_files}: {file_path}"
            )
            try:
                if not _should_analyze(file_path):
                    logger.info(f"⏭️  Skipping unchanged file: {file_path}")
                else:
                    file_size = file_path.stat().st_size
                    t_start = time.perf_counter()
                    await self.analyzer.analyze_file_async(file_path, force=self.force)
                    elapsed = time.perf_counter() - t_start
                    logger.info(
                        f"✅ Analyzed {file_path} | size={file_size} bytes | time={elapsed:.3f}s"
                    )
                    # Vectorization must be handled by the background vectorization worker,
                    # not during analysis. We only mark the file for (re-)chunking.
                    try:
                        self.database.mark_file_needs_chunking(
                            str(file_path.resolve()), self.project_id
                        )
                    except Exception as e:
                        logger.warning(
                            "Failed to mark file for chunking (continuing): %s", e
                        )
                analyzed_count += 1
            except Exception as e:
                logger.error(f"❌ Error analyzing file {file_path}: {e}", exc_info=True)
                analyzed_count += 1  # Count even failed files to continue

            # Update progress every file (10% to 90% range for file analysis)
            if self.progress_tracker and total_files > 0:
                file_progress = 10 + int((analyzed_count / total_files) * 80)
                self.progress_tracker.set_progress(file_progress)
                self.progress_tracker.set_description(
                    f"Analyzing files: {analyzed_count}/{total_files} "
                    f"({file_progress}%) - {file_path.name}"
                )
                # Log every 10th file or last file
                if analyzed_count % 10 == 0 or analyzed_count == total_files:
                    self.progress_tracker.log(
                        f"Analyzed {analyzed_count}/{total_files} files: {file_path}"
                    )
                    logger.info(
                        f"📊 Progress: {analyzed_count}/{total_files} files analyzed ({file_progress}%)"
                    )

        # Get statistics from database for this project
        if self.progress_tracker:
            self.progress_tracker.set_progress(90)
            self.progress_tracker.set_description("Collecting analysis statistics...")

        assert self.database.conn is not None
        cursor = self.database.conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM files WHERE project_id = ?", (self.project_id,)
        )
        files_count = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM classes c
            INNER JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ?
            """,
            (self.project_id,),
        )
        classes_count = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM functions func
            INNER JOIN files f ON func.file_id = f.id
            WHERE f.project_id = ?
            """,
            (self.project_id,),
        )
        functions_count = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM issues WHERE project_id = ?", (self.project_id,)
        )
        issues_count = cursor.fetchone()[0]

        result = {
            "files_analyzed": files_count,
            "classes": classes_count,
            "functions": functions_count,
            "issues": issues_count,
            "project_id": self.project_id,
        }

        completion_msg = (
            f"Analysis complete: {result['files_analyzed']} files, "
            f"{result['classes']} classes, {result['functions']} functions, "
            f"{result['issues']} issues"
        )
        logger.info(completion_msg)

        if self.progress_tracker:
            self.progress_tracker.set_progress(95)
            self.progress_tracker.set_description(completion_msg)
            self.progress_tracker.log(completion_msg)

        # Start vectorization worker in background process if enabled in config.
        # The analyzer does NOT vectorize; the worker does.
        if self.progress_tracker:
            self.progress_tracker.set_description("Starting vectorization worker...")
            self.progress_tracker.log("Starting vectorization worker in background")
        self._start_vectorization_worker()

        if self.progress_tracker:
            self.progress_tracker.set_progress(100)
            self.progress_tracker.set_description("Analysis completed successfully")

        return result

    async def analyze_file(
        self, file_path: Path, force: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze a single Python file and update the database.

        This method is used by the MCP command `analyze_file`. It exists separately
        from `execute()` (project-wide analysis) to avoid `os.walk` and to provide
        a stable API for the command layer.

        Args:
            file_path: Absolute path to the Python file
            force: If True, analyze regardless of modification time checks

        Returns:
            Result dictionary compatible with MCP command expectations.
        """
        try:
            fp = file_path.resolve()
            if not fp.exists() or not fp.is_file():
                return {
                    "success": False,
                    "error": f"File not found or not a file: {fp}",
                    "file_path": str(fp),
                    "project_id": self.project_id,
                }

            t_start = time.perf_counter()
            await self.analyzer.analyze_file_async(fp, force=force)
            elapsed = time.perf_counter() - t_start
            # Mark for background chunking/vectorization (worker will pick it up).
            try:
                self.database.mark_file_needs_chunking(str(fp), self.project_id)
            except Exception as e:
                logger.warning("Failed to mark file for chunking (continuing): %s", e)

            return {
                "success": True,
                "file_path": str(fp),
                "project_id": self.project_id,
                "elapsed_sec": elapsed,
            }
        except Exception as e:
            logger.error("Error analyzing file %s: %s", file_path, e, exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "file_path": str(file_path),
                "project_id": self.project_id,
            }

    def _start_vectorization_worker(self) -> None:
        """
        Start vectorization worker in separate process.

        Worker will process chunks that don't have vector_id yet.
        """
        try:
            from ..core.vectorization_worker import run_vectorization_worker
            from ..core.config import ServerConfig

            # Get configuration from adapter for worker
            svo_config = None
            try:
                from mcp_proxy_adapter.config import get_config as get_adapter_config

                adapter_config = get_adapter_config()
                adapter_config_data = getattr(adapter_config, "config_data", {})
                code_analysis_config = adapter_config_data.get("code_analysis", {})

                if code_analysis_config:
                    server_config = ServerConfig(**code_analysis_config)
                    svo_config = (
                        server_config.model_dump()
                        if hasattr(server_config, "model_dump")
                        else server_config.dict()
                    )
            except Exception as e:
                logger.warning(f"Failed to get config from adapter for worker: {e}")

            if not svo_config:
                logger.info(
                    "Vectorization worker not started (missing code_analysis config)"
                )
                return

            # Build worker inputs from config (not from analyzer runtime objects).
            server_config_obj = ServerConfig(**svo_config)
            worker_cfg = getattr(server_config_obj, "worker", None)
            if worker_cfg is not None and hasattr(worker_cfg, "enabled"):
                if not bool(worker_cfg.enabled):
                    logger.info("Vectorization worker disabled in config")
                    return

            faiss_rel = getattr(server_config_obj, "faiss_index_path", None)
            vector_dim = int(getattr(server_config_obj, "vector_dim", 768) or 768)
            if faiss_rel:
                faiss_index_path = str((self.root_path / str(faiss_rel)).resolve())
            else:
                faiss_index_path = str(
                    (self.root_path / "data" / "faiss_index.bin").resolve()
                )

            # Start worker in separate process
            logger.info("Starting vectorization worker in background process")
            process = multiprocessing.Process(
                target=run_vectorization_worker,
                args=(
                    str(self.database.db_path),
                    self.project_id,
                    faiss_index_path,
                    vector_dim,
                ),
                kwargs={
                    "svo_config": svo_config,
                    "batch_size": 10,
                    "poll_interval": 30,  # Poll every 30 seconds
                },
            )
            process.daemon = True  # Daemon process will be killed when parent exits
            process.start()
            logger.info(f"Vectorization worker started with PID {process.pid}")

        except Exception as e:
            logger.error(f"Failed to start vectorization worker: {e}", exc_info=True)
