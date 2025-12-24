"""
Analyze file command for mcp-proxy-adapter.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# mypy: ignore-errors

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult
from mcp_proxy_adapter.config import get_config as get_adapter_config

from ..core import CodeDatabase
from ..core.progress_tracker import get_progress_tracker_from_context
from .analyze import AnalyzeCommand

logger = logging.getLogger(__name__)


class AnalyzeFileCommand(Command):
    """
    Command for analyzing a single Python file.

    This command analyzes one file and updates the database.
    It does not require queue execution as it's typically fast.
    """

    name = "analyze_file"
    version = "1.0.0"
    descr = "Analyze a single Python file and update database"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False  # File analysis is typically fast, no queue needed

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains data/code_analysis.db)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file (absolute or relative to root_dir)",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines per file threshold",
                    "default": 400,
                },
                "force": {
                    "type": "boolean",
                    "description": "If True, process file regardless of modification time",
                    "default": False,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        max_lines: int = 400,
        force: bool = False,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        """
        Execute file analysis.

        Args:
            root_dir: Root directory of the project
            file_path: Path to Python file (absolute or relative to root_dir)
            max_lines: Maximum lines per file threshold
            force: If True, process file regardless of modification time
            project_id: Optional project UUID

        Returns:
            SuccessResult with analysis results
        """
        try:
            from ..core.svo_client_manager import SVOClientManager
            from ..core.faiss_manager import FaissIndexManager
            from ..core.config import ServerConfig

            root_path = Path(root_dir).resolve()
            if not root_path.exists() or not root_path.is_dir():
                return ErrorResult(
                    message=f"Root directory does not exist or is not a directory: {root_dir}",
                    code="INVALID_PATH",
                )

            # Resolve file path
            file_path_obj = Path(file_path)
            if not file_path_obj.is_absolute():
                file_path_obj = root_path / file_path_obj

            if not file_path_obj.exists():
                return ErrorResult(
                    message=f"File not found: {file_path_obj}",
                    code="FILE_NOT_FOUND",
                )

            if not file_path_obj.is_file():
                return ErrorResult(
                    message=f"Path is not a file: {file_path_obj}",
                    code="NOT_A_FILE",
                )

            # Get configuration from adapter
            adapter_config = get_adapter_config()
            adapter_config_data = getattr(adapter_config, "config_data", {})
            code_analysis_config = adapter_config_data.get("code_analysis", {})

            # Build ServerConfig from adapter config or use defaults
            server_config = None
            if code_analysis_config:
                try:
                    server_config = ServerConfig(**code_analysis_config)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse code_analysis config from adapter: {e}"
                    )
                    server_config = None

            if not server_config:
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
                if project_id:
                    project = database.get_project(project_id)
                    if not project:
                        return ErrorResult(
                            message=f"Project not found: {project_id}",
                            code="PROJECT_NOT_FOUND",
                        )
                    actual_project_id = project_id
                else:
                    actual_project_id = database.get_or_create_project(
                        str(root_path), name=root_path.name
                    )

                # Initialize SVO client manager and FAISS manager if configured
                svo_client_manager = None
                faiss_manager = None

                if server_config and server_config.chunker:
                    try:
                        svo_client_manager = SVOClientManager(server_config)
                        await svo_client_manager.initialize()

                        vector_dim = server_config.vector_dim or 768
                        if server_config.faiss_index_path:
                            faiss_index_path = Path(server_config.faiss_index_path)
                        else:
                            faiss_index_path = root_path / "data" / "faiss_index"

                        faiss_index_path.parent.mkdir(parents=True, exist_ok=True)
                        faiss_manager = FaissIndexManager(
                            str(faiss_index_path), vector_dim
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to initialize SVO/FAISS managers: {e}. "
                            "Continuing without semantic search capabilities."
                        )

                # Get progress tracker from context if available
                context = kwargs.get("context", {})
                progress_tracker = get_progress_tracker_from_context(context)

                # Create and execute analyze command
                analyze_cmd = AnalyzeCommand(
                    database,
                    actual_project_id,
                    str(root_path),
                    max_lines,
                    force=force,
                    svo_client_manager=svo_client_manager,
                    faiss_manager=faiss_manager,
                    progress_tracker=progress_tracker,
                )

                result = await analyze_cmd.analyze_file(file_path_obj, force=force)

                if result.get("success"):
                    return SuccessResult(data=result)
                else:
                    return ErrorResult(
                        message=result.get("error", "File analysis failed"),
                        code="ANALYSIS_ERROR",
                        details=result,
                    )

            finally:
                database.close()

        except Exception as e:
            logger.exception(f"Error during file analysis: {e}")
            return ErrorResult(
                message=f"File analysis failed: {str(e)}",
                code="ANALYSIS_ERROR",
                details={"error": str(e)},
            )
