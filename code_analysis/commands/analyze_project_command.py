"""
Analyze project command for mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Import patch for CommandExecutionJob to support progress tracking
# This must be imported before CommandExecutionJob is used
from ..core.command_execution_job_patch import patch_command_execution_job  # noqa: F401

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult
from mcp_proxy_adapter.config import get_config as get_adapter_config

from ..core import CodeDatabase
from ..core.progress_tracker import get_progress_tracker_from_context
from .analyze import AnalyzeCommand

# Use logger from adapter (configured by adapter)
logger = logging.getLogger(__name__)


class AnalyzeProjectCommand(Command):
    """
    Command for analyzing Python projects via queue.

    CRITICAL: This command MUST execute via queue (use_queue=True).
    Analysis is a long-running operation that can take minutes or hours
    depending on project size. Queue execution ensures:
    - Non-blocking server responses
    - Progress tracking
    - Job status monitoring
    - Proper resource management

    DO NOT set use_queue=False for this command.
    """

    name = "analyze_project"
    version = "1.0.0"
    descr = "Analyze Python project and generate code map with semantic embeddings"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    # CRITICAL: This command MUST execute via queue
    # Analysis is a long-running operation that requires queue execution
    use_queue = (
        True  # REQUIRED: Enable automatic queue execution for long-running operation
    )

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        schema = {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project to analyze",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines per file threshold",
                    "default": 400,
                },
                "comment": {
                    "type": "string",
                    "description": "Optional human-readable comment/identifier for the project",
                },
                "force": {
                    "type": "boolean",
                    "description": "If True, process all files regardless of modification time",
                    "default": False,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds for the analysis",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }
        # Add metadata about queue usage
        if hasattr(cls, "use_queue") and cls.use_queue:
            schema["x-use-queue"] = True
        return schema

    async def execute(
        self,
        root_dir: str,
        max_lines: int = 400,
        comment: Optional[str] = None,
        force: bool = False,
        **kwargs,
    ) -> SuccessResult:
        """
        Execute project analysis.

        Args:
            root_dir: Root directory of the project to analyze
            max_lines: Maximum lines per file threshold
            comment: Optional human-readable comment/identifier for the project
            force: If True, process all files regardless of modification time

        Returns:
            SuccessResult with analysis results
        """
        try:
            from ..core.config import ServerConfig

            root_path = Path(root_dir).resolve()
            if not root_path.exists() or not root_path.is_dir():
                return ErrorResult(
                    message=f"Root directory does not exist or is not a directory: {root_dir}",
                    code="INVALID_PATH",
                )

            # Get configuration from adapter (not self-written ConfigManager)
            # Adapter config is set up in main.py and available globally
            adapter_config = get_adapter_config()
            adapter_config_data = getattr(adapter_config, "config_data", {})

            # Extract code-analysis specific configuration from adapter config
            # Look for code_analysis section in adapter config, or use defaults
            code_analysis_config = adapter_config_data.get("code_analysis", {})

            # Build ServerConfig from adapter config or use defaults
            server_config = None
            if code_analysis_config:
                try:
                    # Try to build ServerConfig from code_analysis section
                    server_config = ServerConfig(**code_analysis_config)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse code_analysis config from adapter: {e}"
                    )
                    server_config = None

            if not server_config:
                # Create minimal default configuration
                logger.info(
                    "No code_analysis configuration found in adapter config, using defaults"
                )
                server_config = ServerConfig(
                    host="0.0.0.0",
                    port=15000,
                    log=None,
                    db_path=None,
                    dirs=[],
                    chunker=None,
                    faiss_index_path=None,
                    vector_dim=None,
                )

            # Initialize database
            data_dir = root_path / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = data_dir / "code_analysis.db"
            database = CodeDatabase(db_path)

            try:
                # Get or create project
                project_id = database.get_or_create_project(
                    str(root_path), name=root_path.name, comment=comment
                )

                # IMPORTANT:
                # Vectorization/chunking must be performed by the background vectorization worker,
                # not by the analyzer during project analysis. We intentionally do NOT initialize
                # SVO/FAISS managers here to keep analysis deterministic and fast.
                svo_client_manager = None
                faiss_manager = None

                # Get progress tracker from context if available
                context = kwargs.get("context", {})
                progress_tracker = get_progress_tracker_from_context(context)

                # Create and execute analyze command
                analyze_cmd = AnalyzeCommand(
                    database,
                    project_id,
                    str(root_path),
                    max_lines,
                    force=force,
                    svo_client_manager=svo_client_manager,
                    faiss_manager=faiss_manager,
                    progress_tracker=progress_tracker,
                )

                result = await analyze_cmd.execute()

                return SuccessResult(
                    data={
                        "files_analyzed": result["files_analyzed"],
                        "classes": result["classes"],
                        "functions": result["functions"],
                        "issues": result["issues"],
                        "project_id": result["project_id"],
                    }
                )

            finally:
                database.close()

        except Exception as e:
            logger.exception(f"Error during project analysis: {e}")
            return ErrorResult(
                message=f"Analysis failed: {str(e)}",
                code="ANALYSIS_ERROR",
                details={"error": str(e)},
            )
