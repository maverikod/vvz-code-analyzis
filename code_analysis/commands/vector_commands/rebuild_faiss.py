"""
MCP command for rebuilding FAISS index.

One index per project: {faiss_dir}/{project_id}.bin.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ...core.faiss_manager import FaissIndexManager
from ...core.storage_paths import resolve_storage_paths, get_faiss_index_path
from ...core.project_resolution import normalize_root_dir

logger = logging.getLogger(__name__)


class RebuildFaissCommand(BaseMCPCommand):
    """
    Rebuild FAISS index from database.

    One index per project. Rebuilds the single FAISS index for the project.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Human readable description.
        category: Command category.
        author: Author name.
        email: Author email.
        use_queue: Whether command runs via queue.
    """

    name = "rebuild_faiss"
    version = "1.0.0"
    descr = "Rebuild FAISS index from database (one index per project)"
    category = "vectorization"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["RebuildFaissCommand"]) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema describing command parameters.
        """
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory of the project (contains projectid file)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (must match root_dir/projectid)",
                },
            },
            "required": ["root_dir", "project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self: "RebuildFaissCommand",
        root_dir: str,
        project_id: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute FAISS index rebuild (one index per project).

        Args:
            self: Command instance.
            root_dir: Root directory of the project.
            project_id: Project UUID (must match root_dir/projectid).

        Returns:
            SuccessResult with rebuild statistics or ErrorResult on failure.
        """
        try:
            root_path = normalize_root_dir(root_dir)

            # Validate project_id matches root_dir/projectid
            self._require_project_id_gate(root_dir, project_id)

            database = self._open_database(root_dir)
            try:
                actual_project_id = self._get_project_id(
                    database, root_path, project_id
                )
                if not actual_project_id:
                    return ErrorResult(
                        message=f"Project not found: {project_id}",
                        code="PROJECT_NOT_FOUND",
                    )

                # Resolve storage paths
                config_path = root_path / "config.json"
                if not config_path.exists():
                    return ErrorResult(
                        message=f"Configuration file not found: {config_path}",
                        code="CONFIG_NOT_FOUND",
                    )

                import json

                with open(config_path, "r", encoding="utf-8") as f:
                    config_dict = json.load(f)

                storage_paths = resolve_storage_paths(
                    config_data=config_dict, config_path=config_path
                )

                # Get vector dimension
                code_analysis_config = config_dict.get("code_analysis", config_dict)
                vector_dim = int(code_analysis_config.get("vector_dim", 384))

                # One index per project: {faiss_dir}/{project_id}.bin
                index_path = get_faiss_index_path(
                    storage_paths.faiss_dir, actual_project_id
                )

                # Initialize SVO client manager
                from ...core.svo_client_manager import SVOClientManager

                svo_client_manager = SVOClientManager(config_dict, root_dir=root_path)
                await svo_client_manager.initialize()

                try:
                    faiss_manager = FaissIndexManager(
                        index_path=str(index_path),
                        vector_dim=vector_dim,
                    )

                    vectors_count = await faiss_manager.rebuild_from_database(
                        database,
                        svo_client_manager,
                        project_id=actual_project_id,
                    )

                    faiss_manager.close()

                    return SuccessResult(
                        data={
                            "project_id": actual_project_id,
                            "index_path": str(index_path),
                            "vectors_count": vectors_count,
                        }
                    )
                finally:
                    await svo_client_manager.close()
            finally:
                database.disconnect()

        except Exception as e:
            logger.error(f"Failed to rebuild FAISS index: {e}", exc_info=True)
            return self._handle_error(e, "REBUILD_FAISS_ERROR", "rebuild_faiss")

    @classmethod
    def metadata(cls: type["RebuildFaissCommand"]) -> Dict[str, Any]:
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
                "The rebuild_faiss command rebuilds FAISS (Facebook AI Similarity Search) "
                "index from database embeddings. One index per project: {faiss_dir}/{project_id}.bin.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Validates project_id matches root_dir/projectid file\n"
                "3. Opens database connection\n"
                "4. Verifies project exists in database\n"
                "5. Loads config.json to get storage paths and vector dimension\n"
                "6. Initializes SVOClientManager for embeddings\n"
                "7. Gets project-scoped FAISS index path\n"
                "8. Rebuilds FAISS index from database embeddings (all chunks in project)\n"
                "9. Returns rebuild statistics\n\n"
                "FAISS Index:\n"
                "- One index per project: {faiss_dir}/{project_id}.bin\n"
                "- Reads embeddings from code_chunks.embedding_vector in database\n"
                "- Normalizes vector_id to dense range 0..N-1\n"
                "- Requires valid embeddings in database (use revectorize if missing)\n"
                "- project_id must match root_dir/projectid file"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain projectid file and config.json."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project",
                        ".",
                        "./code_analysis",
                    ],
                },
                "project_id": {
                    "description": (
                        "Project UUID. Must match the UUID in root_dir/projectid file. "
                        "Used to identify project and resolve FAISS index path."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "123e4567-e89b-12d3-a456-426614174000",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Rebuild FAISS index for project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                    },
                    "explanation": "Rebuilds the single FAISS index for the project.",
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "message": "Project not found: {project_id}",
                    "solution": (
                        "Verify project_id is correct. Ensure project is registered in database. "
                        "Run update_indexes to register project if needed."
                    ),
                },
                "CONFIG_NOT_FOUND": {
                    "description": "Configuration file not found",
                    "message": "Configuration file not found: {config_path}",
                    "solution": (
                        "Ensure config.json exists in root_dir. "
                        "Config file is required for storage paths and vector dimension."
                    ),
                },
                "REBUILD_FAISS_ERROR": {
                    "description": "Error during FAISS index rebuild",
                    "examples": [
                        {
                            "case": "Missing embeddings",
                            "message": "No embeddings found in database",
                            "solution": (
                                "Run revectorize first to generate embeddings. "
                                "rebuild_faiss requires existing embeddings in database."
                            ),
                        },
                        {
                            "case": "Vector dimension mismatch",
                            "message": "Vector dimension mismatch",
                            "solution": (
                                "Verify vector_dim in config.json matches embedding dimension. "
                                "Check SVO service configuration."
                            ),
                        },
                        {
                            "case": "FAISS library error",
                            "message": "FAISS index creation failed",
                            "solution": (
                                "Check FAISS library installation. "
                                "Verify disk space and permissions for index directory."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "FAISS index rebuilt successfully",
                    "data": {
                        "project_id": "Project UUID",
                        "index_path": "Path to FAISS index file ({faiss_dir}/{project_id}.bin)",
                        "vectors_count": "Number of vectors in index",
                    },
                    "example": {
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "index_path": "/data/faiss/123e4567-e89b-12d3-a456-426614174000.bin",
                        "vectors_count": 5000,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, REBUILD_FAISS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Run revectorize first if embeddings are missing",
                "Rebuild index after bulk embedding updates",
                "Verify vectors_count matches expected number of chunks",
                "Check index_path to verify index file location",
                "Ensure vector_dim in config matches embedding dimension",
            ],
        }
