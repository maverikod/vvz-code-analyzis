"""
MCP command for rebuilding FAISS index.

Implements dataset-scoped FAISS (Step 2 of refactor plan).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..base_mcp_command import BaseMCPCommand
from ...core.faiss_manager import FaissIndexManager
from ...core.storage_paths import resolve_storage_paths, get_faiss_index_path
from ...core.project_resolution import normalize_root_dir

logger = logging.getLogger(__name__)


class RebuildFaissCommand(BaseMCPCommand):
    """
    Rebuild FAISS index from database.

    Implements dataset-scoped FAISS (Step 2 of refactor plan).
    Rebuilds FAISS index for a specific dataset or all datasets in a project.

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
    descr = "Rebuild FAISS index from database (dataset-scoped)"
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
                "dataset_id": {
                    "type": "string",
                    "description": "Optional dataset UUID; if omitted, rebuilds all datasets in project",
                },
            },
            "required": ["root_dir", "project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self: "RebuildFaissCommand",
        root_dir: str,
        project_id: str,
        dataset_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute FAISS index rebuild.

        Args:
            self: Command instance.
            root_dir: Root directory of the project.
            project_id: Project UUID (must match root_dir/projectid).
            dataset_id: Optional dataset UUID; if omitted, rebuilds all datasets.

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

                # Initialize SVO client manager
                from ...core.svo_client_manager import SVOClientManager

                svo_client_manager = SVOClientManager(config_dict, root_dir=root_path)
                await svo_client_manager.initialize()

                try:
                    results = []

                    if dataset_id:
                        # Rebuild index for specific dataset
                        normalized_root = str(normalize_root_dir(root_dir))
                        from ...commands.base_mcp_command import BaseMCPCommand

                        db_dataset_id = BaseMCPCommand._get_dataset_id(
                            database, actual_project_id, normalized_root
                        )
                        if not db_dataset_id:
                            # Create dataset if it doesn't exist
                            from ...commands.base_mcp_command import BaseMCPCommand

                            db_dataset_id = BaseMCPCommand._get_or_create_dataset(
                                database, actual_project_id, normalized_root
                            )

                        if db_dataset_id != dataset_id:
                            return ErrorResult(
                                message=f"Dataset ID mismatch: provided {dataset_id}, found {db_dataset_id}",
                                code="DATASET_ID_MISMATCH",
                            )

                        # Get dataset-scoped FAISS index path
                        index_path = get_faiss_index_path(
                            storage_paths.faiss_dir, actual_project_id, dataset_id
                        )

                        # Initialize FAISS manager
                        faiss_manager = FaissIndexManager(
                            index_path=str(index_path),
                            vector_dim=vector_dim,
                        )

                        # Rebuild index
                        vectors_count = await faiss_manager.rebuild_from_database(
                            database,
                            svo_client_manager,
                            project_id=actual_project_id,
                            dataset_id=dataset_id,
                        )

                        results.append(
                            {
                                "dataset_id": dataset_id,
                                "index_path": str(index_path),
                                "vectors_count": vectors_count,
                            }
                        )

                        faiss_manager.close()
                    else:
                        # Rebuild indexes for all datasets in project
                        datasets = database.get_project_datasets(actual_project_id)
                        if not datasets:
                            return ErrorResult(
                                message=f"No datasets found for project {actual_project_id}",
                                code="NO_DATASETS",
                            )

                        for dataset in datasets:
                            ds_id = dataset["id"]
                            ds_root = dataset["root_path"]

                            # Get dataset-scoped FAISS index path
                            index_path = get_faiss_index_path(
                                storage_paths.faiss_dir, actual_project_id, ds_id
                            )

                            # Initialize FAISS manager
                            faiss_manager = FaissIndexManager(
                                index_path=str(index_path),
                                vector_dim=vector_dim,
                            )

                            # Rebuild index
                            vectors_count = await faiss_manager.rebuild_from_database(
                                database,
                                svo_client_manager,
                                project_id=actual_project_id,
                                dataset_id=ds_id,
                            )

                            results.append(
                                {
                                    "dataset_id": ds_id,
                                    "root_path": ds_root,
                                    "index_path": str(index_path),
                                    "vectors_count": vectors_count,
                                }
                            )

                            faiss_manager.close()

                    total_vectors = sum(r["vectors_count"] for r in results)

                    return SuccessResult(
                        data={
                            "project_id": actual_project_id,
                            "datasets_rebuilt": len(results),
                            "total_vectors": total_vectors,
                            "results": results,
                        }
                    )
                finally:
                    await svo_client_manager.close()
            finally:
                database.close()

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
                "index from database embeddings. It implements dataset-scoped FAISS, allowing "
                "rebuilding indexes for specific datasets or all datasets in a project.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Validates project_id matches root_dir/projectid file\n"
                "3. Opens database connection\n"
                "4. Verifies project exists in database\n"
                "5. Loads config.json to get storage paths and vector dimension\n"
                "6. Initializes SVOClientManager for embeddings\n"
                "7. If dataset_id provided: rebuilds index for that dataset\n"
                "8. If dataset_id omitted: rebuilds indexes for all datasets in project\n"
                "9. For each dataset:\n"
                "   - Gets dataset-scoped FAISS index path\n"
                "   - Initializes FaissIndexManager\n"
                "   - Normalizes vector_id to dense range (0..N-1)\n"
                "   - Rebuilds FAISS index from database embeddings\n"
                "   - Closes FAISS manager\n"
                "10. Returns rebuild statistics\n\n"
                "FAISS Index Rebuilding:\n"
                "- Reads embeddings from code_chunks.embedding_vector in database\n"
                "- Normalizes vector_id to dense range to avoid ID conflicts\n"
                "- Creates new FAISS index file from embeddings\n"
                "- Index is dataset-scoped (one index per dataset)\n"
                "- Index path: {faiss_dir}/{project_id}/{dataset_id}/index.faiss\n\n"
                "Vector ID Normalization:\n"
                "- Reassigns vector_id to dense range 0..N-1\n"
                "- Uses single SQL statement to avoid per-row UPDATEs\n"
                "- Prevents ID conflicts and stabilizes sqlite_proxy worker\n"
                "- Only processes chunks with valid embeddings\n\n"
                "Dataset-Scoped FAISS:\n"
                "- Each dataset has its own FAISS index file\n"
                "- Allows independent index management per dataset\n"
                "- Supports multiple datasets per project\n"
                "- Indexes are stored in separate directories\n\n"
                "Use cases:\n"
                "- Rebuild index after database changes\n"
                "- Recover from corrupted index file\n"
                "- Rebuild index after embedding updates\n"
                "- Initialize index for new dataset\n"
                "- Sync index with database state\n"
                "- Rebuild all indexes after project changes\n\n"
                "Important notes:\n"
                "- Requires valid embeddings in database (use revectorize if missing)\n"
                "- Rebuilds index from existing embeddings (doesn't generate new ones)\n"
                "- Index file is recreated (old index is replaced)\n"
                "- Vector dimension must match config.json setting\n"
                "- Requires SVOClientManager for missing embeddings (if any)\n"
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
                        "Used to identify project and resolve dataset indexes."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "123e4567-e89b-12d3-a456-426614174000",
                    ],
                },
                "dataset_id": {
                    "description": (
                        "Optional dataset UUID. If provided, rebuilds index only for that dataset. "
                        "If omitted, rebuilds indexes for all datasets in the project. "
                        "Dataset must exist in database."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "223e4567-e89b-12d3-a456-426614174001",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Rebuild index for specific dataset",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "dataset_id": "223e4567-e89b-12d3-a456-426614174001",
                    },
                    "explanation": (
                        "Rebuilds FAISS index for specific dataset. "
                        "Useful when only one dataset needs index update."
                    ),
                },
                {
                    "description": "Rebuild indexes for all datasets",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                    },
                    "explanation": (
                        "Rebuilds FAISS indexes for all datasets in the project. "
                        "Useful after project-wide changes."
                    ),
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
                "DATASET_ID_MISMATCH": {
                    "description": "Dataset ID mismatch",
                    "message": "Dataset ID mismatch: provided {dataset_id}, found {db_dataset_id}",
                    "solution": (
                        "Verify dataset_id is correct. Dataset ID in database must match provided ID. "
                        "Use list_projects or database queries to find correct dataset_id."
                    ),
                },
                "NO_DATASETS": {
                    "description": "No datasets found for project",
                    "message": "No datasets found for project {project_id}",
                    "solution": (
                        "Ensure project has datasets. Run update_indexes to create datasets. "
                        "Datasets are created automatically when indexing files."
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
                        "project_id": "Project UUID that was processed",
                        "datasets_rebuilt": "Number of datasets processed",
                        "total_vectors": "Total number of vectors in all indexes",
                        "results": (
                            "List of rebuild results. Each contains:\n"
                            "- dataset_id: Dataset UUID\n"
                            "- index_path: Path to FAISS index file\n"
                            "- vectors_count: Number of vectors in index\n"
                            "- root_path: Dataset root path (if all datasets)"
                        ),
                    },
                    "example_single_dataset": {
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "datasets_rebuilt": 1,
                        "total_vectors": 5000,
                        "results": [
                            {
                                "dataset_id": "223e4567-e89b-12d3-a456-426614174001",
                                "index_path": "/data/faiss/123e4567.../223e4567.../index.faiss",
                                "vectors_count": 5000,
                            }
                        ],
                    },
                    "example_multiple_datasets": {
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "datasets_rebuilt": 3,
                        "total_vectors": 15000,
                        "results": [
                            {
                                "dataset_id": "223e4567-e89b-12d3-a456-426614174001",
                                "root_path": "/path/to/dataset1",
                                "index_path": "/data/faiss/123e4567.../223e4567.../index.faiss",
                                "vectors_count": 5000,
                            },
                            {
                                "dataset_id": "323e4567-e89b-12d3-a456-426614174002",
                                "root_path": "/path/to/dataset2",
                                "index_path": "/data/faiss/123e4567.../323e4567.../index.faiss",
                                "vectors_count": 7000,
                            },
                            {
                                "dataset_id": "423e4567-e89b-12d3-a456-426614174003",
                                "root_path": "/path/to/dataset3",
                                "index_path": "/data/faiss/123e4567.../423e4567.../index.faiss",
                                "vectors_count": 3000,
                            },
                        ],
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": (
                        "Error code (e.g., PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, "
                        "DATASET_ID_MISMATCH, NO_DATASETS, REBUILD_FAISS_ERROR)"
                    ),
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Run revectorize first if embeddings are missing",
                "Rebuild index after bulk embedding updates",
                "Use dataset_id to rebuild specific dataset index",
                "Rebuild all datasets after project-wide changes",
                "Verify vectors_count matches expected number of chunks",
                "Check index_path to verify index file location",
                "Monitor total_vectors to track index size",
                "Rebuild index after database repairs or restores",
                "Ensure vector_dim in config matches embedding dimension",
            ],
        }
