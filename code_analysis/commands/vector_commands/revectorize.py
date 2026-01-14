"""
MCP command for revectorizing chunks.

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


class RevectorizeCommand(BaseMCPCommand):
    """
    Revectorize chunks (regenerate embeddings and update FAISS index).

    Implements dataset-scoped FAISS (Step 2 of refactor plan).
    Revectorizes chunks for a specific dataset or all datasets in a project.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Human readable description.
        category: Command category.
        author: Author name.
        email: Author email.
        use_queue: Whether command runs via queue.
    """

    name = "revectorize"
    version = "1.0.0"
    descr = "Revectorize chunks (regenerate embeddings and update FAISS index)"
    category = "vectorization"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["RevectorizeCommand"]) -> Dict[str, Any]:
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
                    "description": "Optional dataset UUID; if omitted, revectorizes all datasets in project",
                },
                "force": {
                    "type": "boolean",
                    "description": "Force revectorization even if embeddings exist (default: false)",
                    "default": False,
                },
            },
            "required": ["root_dir", "project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self: "RevectorizeCommand",
        root_dir: str,
        project_id: str,
        dataset_id: Optional[str] = None,
        force: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute chunk revectorization.

        Args:
            self: Command instance.
            root_dir: Root directory of the project.
            project_id: Project UUID (must match root_dir/projectid).
            dataset_id: Optional dataset UUID; if omitted, revectorizes all datasets.
            force: Force revectorization even if embeddings exist.

        Returns:
            SuccessResult with revectorization statistics or ErrorResult on failure.
        """
        try:
            root_path = normalize_root_dir(root_dir)

            # Validate project_id matches root_dir/projectid
            self._require_project_id_gate(root_dir, project_id)

            database = self._open_database(root_dir)
            try:
                actual_project_id = self._get_project_id(database, root_path, project_id)
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
                        # Revectorize chunks for specific dataset
                        normalized_root = str(normalize_root_dir(root_dir))
                        db_dataset_id = database.get_dataset_id(actual_project_id, normalized_root)
                        if not db_dataset_id:
                            # Create dataset if it doesn't exist
                            db_dataset_id = database.get_or_create_dataset(
                                actual_project_id, normalized_root
                            )

                        if db_dataset_id != dataset_id:
                            return ErrorResult(
                                message=f"Dataset ID mismatch: provided {dataset_id}, found {db_dataset_id}",
                                code="DATASET_ID_MISMATCH",
                            )

                        result = await self._revectorize_dataset(
                            database,
                            svo_client_manager,
                            storage_paths,
                            actual_project_id,
                            dataset_id,
                            vector_dim,
                            force,
                        )
                        results.append(result)
                    else:
                        # Revectorize chunks for all datasets in project
                        datasets = database.get_project_datasets(actual_project_id)
                        if not datasets:
                            return ErrorResult(
                                message=f"No datasets found for project {actual_project_id}",
                                code="NO_DATASETS",
                            )

                        for dataset in datasets:
                            ds_id = dataset["id"]
                            result = await self._revectorize_dataset(
                                database,
                                svo_client_manager,
                                storage_paths,
                                actual_project_id,
                                ds_id,
                                vector_dim,
                                force,
                            )
                            results.append(result)

                    total_chunks = sum(r["chunks_revectorized"] for r in results)

                    return SuccessResult(
                        data={
                            "project_id": actual_project_id,
                            "datasets_processed": len(results),
                            "total_chunks_revectorized": total_chunks,
                            "results": results,
                        }
                    )
                finally:
                    await svo_client_manager.close()
            finally:
                database.close()

        except Exception as e:
            logger.error(f"Failed to revectorize chunks: {e}", exc_info=True)
            return self._handle_error(e, "REVECTORIZE_ERROR", "revectorize")

    @classmethod
    def metadata(cls: type["RevectorizeCommand"]) -> Dict[str, Any]:
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
                "The revectorize command regenerates embeddings for code chunks and updates "
                "the FAISS index. It implements dataset-scoped FAISS, allowing revectorization "
                "for specific datasets or all datasets in a project.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Validates project_id matches root_dir/projectid file\n"
                "3. Opens database connection\n"
                "4. Verifies project exists in database\n"
                "5. Loads config.json to get storage paths and vector dimension\n"
                "6. Initializes SVOClientManager for embedding generation\n"
                "7. If dataset_id provided: revectorizes chunks for that dataset\n"
                "8. If dataset_id omitted: revectorizes chunks for all datasets in project\n"
                "9. For each dataset:\n"
                "   - Gets chunks that need revectorization\n"
                "   - For each chunk:\n"
                "     * Gets chunk text\n"
                "     * Calls SVO service to generate embedding\n"
                "     * Updates database with new embedding\n"
                "     * Sets vector_id to NULL (will be reassigned on rebuild)\n"
                "   - Rebuilds FAISS index from updated embeddings\n"
                "10. Returns revectorization statistics\n\n"
                "Revectorization Process:\n"
                "- Finds chunks without embeddings or with force=True (all chunks)\n"
                "- Generates new embeddings using SVO (Semantic Vector Operations) service\n"
                "- Updates code_chunks.embedding_vector in database\n"
                "- Updates code_chunks.embedding_model with model name\n"
                "- Sets vector_id to NULL (normalized during FAISS rebuild)\n"
                "- Rebuilds FAISS index after revectorization\n\n"
                "Force Mode:\n"
                "- If force=False: Only revectorizes chunks without embeddings\n"
                "- If force=True: Revectorizes all chunks (regenerates all embeddings)\n"
                "- Use force=True to update embeddings after model changes\n"
                "- Use force=False to only process missing embeddings\n\n"
                "Embedding Generation:\n"
                "- Uses SVOClientManager to call embedding service\n"
                "- Embeddings are generated asynchronously\n"
                "- Vector dimension comes from config.json (default: 384)\n"
                "- Embeddings are stored as JSON arrays in database\n"
                "- Model name is stored for tracking embedding source\n\n"
                "FAISS Index Update:\n"
                "- After revectorization, FAISS index is rebuilt\n"
                "- Rebuild normalizes vector_id to dense range\n"
                "- Index includes all chunks with valid embeddings\n"
                "- Index is dataset-scoped (one per dataset)\n\n"
                "Use cases:\n"
                "- Generate embeddings for chunks without vectors\n"
                "- Regenerate embeddings after model changes\n"
                "- Update embeddings for improved quality\n"
                "- Initialize embeddings for new chunks\n"
                "- Fix corrupted or invalid embeddings\n"
                "- Revectorize after embedding service updates\n\n"
                "Important notes:\n"
                "- Requires SVO service to be configured and accessible\n"
                "- Embedding generation can be slow for many chunks\n"
                "- FAISS index is automatically rebuilt after revectorization\n"
                "- force=True regenerates all embeddings (can be time-consuming)\n"
                "- Chunks with empty text are skipped\n"
                "- Failed chunks are logged but don't stop the process\n"
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
                        "Used to identify project and resolve dataset chunks."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "123e4567-e89b-12d3-a456-426614174000",
                    ],
                },
                "dataset_id": {
                    "description": (
                        "Optional dataset UUID. If provided, revectorizes chunks only for that dataset. "
                        "If omitted, revectorizes chunks for all datasets in the project. "
                        "Dataset must exist in database."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "223e4567-e89b-12d3-a456-426614174001",
                    ],
                },
                "force": {
                    "description": (
                        "If True, force revectorization even if embeddings exist. "
                        "Regenerates all embeddings. If False, only processes chunks without embeddings. "
                        "Default is False."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                    "examples": [False, True],
                },
            },
            "usage_examples": [
                {
                    "description": "Revectorize missing embeddings for specific dataset",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "dataset_id": "223e4567-e89b-12d3-a456-426614174001",
                        "force": False,
                    },
                    "explanation": (
                        "Revectorizes only chunks without embeddings for specific dataset. "
                        "FAISS index is automatically rebuilt after completion."
                    ),
                },
                {
                    "description": "Force revectorize all chunks",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "force": True,
                    },
                    "explanation": (
                        "Regenerates all embeddings for all datasets in project. "
                        "Useful after embedding model changes."
                    ),
                },
                {
                    "description": "Revectorize all datasets",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                    },
                    "explanation": (
                        "Revectorizes missing embeddings for all datasets in project. "
                        "Processes chunks without embeddings only."
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
                        "Config file is required for SVO service configuration."
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
                "REVECTORIZE_ERROR": {
                    "description": "Error during revectorization",
                    "examples": [
                        {
                            "case": "SVO service unavailable",
                            "message": "Failed to connect to SVO service",
                            "solution": (
                                "Check SVO service configuration in config.json. "
                                "Verify service is running and accessible."
                            ),
                        },
                        {
                            "case": "Embedding generation failed",
                            "message": "Failed to generate embedding",
                            "solution": (
                                "Check SVO service logs. Verify chunk text is valid. "
                                "Some chunks may fail but process continues."
                            ),
                        },
                        {
                            "case": "Database update error",
                            "message": "Failed to update database",
                            "solution": (
                                "Check database integrity. Verify write permissions. "
                                "Check database connection."
                            ),
                        },
                    ],
                },
            },
            "return_value": {
                "success": {
                    "description": "Revectorization completed successfully",
                    "data": {
                        "project_id": "Project UUID that was processed",
                        "datasets_processed": "Number of datasets processed",
                        "total_chunks_revectorized": "Total number of chunks revectorized",
                        "results": (
                            "List of revectorization results. Each contains:\n"
                            "- dataset_id: Dataset UUID\n"
                            "- chunks_revectorized: Number of chunks revectorized\n"
                            "- vectors_in_index: Number of vectors in rebuilt FAISS index\n"
                            "- index_path: Path to FAISS index file"
                        ),
                    },
                    "example_single_dataset": {
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "datasets_processed": 1,
                        "total_chunks_revectorized": 500,
                        "results": [
                            {
                                "dataset_id": "223e4567-e89b-12d3-a456-426614174001",
                                "chunks_revectorized": 500,
                                "vectors_in_index": 5000,
                                "index_path": "/data/faiss/123e4567.../223e4567.../index.faiss",
                            }
                        ],
                    },
                    "example_multiple_datasets": {
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "datasets_processed": 3,
                        "total_chunks_revectorized": 1200,
                        "results": [
                            {
                                "dataset_id": "223e4567-e89b-12d3-a456-426614174001",
                                "chunks_revectorized": 500,
                                "vectors_in_index": 5000,
                                "index_path": "/data/faiss/123e4567.../223e4567.../index.faiss",
                            },
                            {
                                "dataset_id": "323e4567-e89b-12d3-a456-426614174002",
                                "chunks_revectorized": 400,
                                "vectors_in_index": 7000,
                                "index_path": "/data/faiss/123e4567.../323e4567.../index.faiss",
                            },
                            {
                                "dataset_id": "423e4567-e89b-12d3-a456-426614174003",
                                "chunks_revectorized": 300,
                                "vectors_in_index": 3000,
                                "index_path": "/data/faiss/123e4567.../423e4567.../index.faiss",
                            },
                        ],
                    },
                    "example_no_chunks": {
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "datasets_processed": 1,
                        "total_chunks_revectorized": 0,
                        "results": [
                            {
                                "dataset_id": "223e4567-e89b-12d3-a456-426614174001",
                                "chunks_revectorized": 0,
                                "index_path": "/data/faiss/123e4567.../223e4567.../index.faiss",
                            }
                        ],
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": (
                        "Error code (e.g., PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, "
                        "DATASET_ID_MISMATCH, NO_DATASETS, REVECTORIZE_ERROR)"
                    ),
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use force=False to only process missing embeddings (faster)",
                "Use force=True after embedding model changes",
                "Run revectorize before rebuild_faiss if embeddings are missing",
                "Monitor chunks_revectorized to track progress",
                "Check vectors_in_index to verify FAISS index was rebuilt",
                "Use dataset_id to revectorize specific dataset",
                "Revectorize all datasets after model updates",
                "Ensure SVO service is configured and accessible",
                "Monitor logs for failed chunk revectorization",
                "Run rebuild_faiss after revectorize to ensure index is updated",
            ],
        }

    async def _revectorize_dataset(
        self,
        database: Any,
        svo_client_manager: Any,
        storage_paths: Any,
        project_id: str,
        dataset_id: str,
        vector_dim: int,
        force: bool,
    ) -> Dict[str, Any]:
        """Revectorize chunks for a specific dataset.

        Args:
            database: DatabaseClient instance.
            svo_client_manager: SVOClientManager instance.
            storage_paths: StoragePaths instance.
            project_id: Project UUID.
            dataset_id: Dataset UUID.
            vector_dim: Vector dimension.
            force: Force revectorization even if embeddings exist.

        Returns:
            Dictionary with revectorization statistics.
        """
        # Get dataset-scoped FAISS index path
        index_path = get_faiss_index_path(
            storage_paths.faiss_dir, project_id, dataset_id
        )

        # Initialize FAISS manager
        faiss_manager = FaissIndexManager(
            index_path=str(index_path),
            vector_dim=vector_dim,
        )

        try:
            # Get chunks for this dataset that need revectorization
            # If force=True, get all chunks; otherwise get only chunks without embeddings
            if force:
                # Get all chunks for this dataset
                chunks = database.get_all_chunks_for_faiss_rebuild(
                    project_id=project_id, dataset_id=dataset_id
                )
            else:
                # Get only chunks without embeddings
                # This is a simplified version - in production, you might want a more sophisticated query
                chunks = database.get_all_chunks_for_faiss_rebuild(
                    project_id=project_id, dataset_id=dataset_id
                )
                # Filter chunks without embeddings
                chunks = [
                    c
                    for c in chunks
                    if not c.get("embedding_vector") or not c.get("embedding_model")
                ]

            if not chunks:
                return {
                    "dataset_id": dataset_id,
                    "chunks_revectorized": 0,
                    "index_path": str(index_path),
                }

            # Revectorize chunks and update FAISS index
            revectorized_count = 0
            for chunk in chunks:
                chunk_id = chunk.get("id")
                chunk_text = chunk.get("chunk_text", "")

                if not chunk_text:
                    continue

                try:
                    # Get new embedding from SVO service
                    class _TmpChunk:
                        def __init__(self, text: str):
                            self.body = text
                            self.text = text

                    tmp = _TmpChunk(chunk_text)
                    chunks_with_emb = await svo_client_manager.get_embeddings([tmp])
                    if chunks_with_emb and hasattr(chunks_with_emb[0], "embedding"):
                        embedding = getattr(chunks_with_emb[0], "embedding")
                        embedding_model = getattr(
                            chunks_with_emb[0], "embedding_model", None
                        )

                        if embedding is not None:
                            import json
                            import numpy as np

                            embedding_array = np.array(embedding, dtype="float32")
                            embedding_json = json.dumps(embedding_array.tolist())

                            # Update database with new embedding
                            database._execute(
                                """
                                UPDATE code_chunks
                                SET embedding_vector = ?, embedding_model = ?, vector_id = NULL
                                WHERE id = ?
                                """,
                                (embedding_json, embedding_model, chunk_id),
                            )
                            database._commit()

                            revectorized_count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to revectorize chunk {chunk_id}: {e}", exc_info=True
                    )

            # Rebuild FAISS index for this dataset
            vectors_count = await faiss_manager.rebuild_from_database(
                database,
                svo_client_manager,
                project_id=project_id,
                dataset_id=dataset_id,
            )

            return {
                "dataset_id": dataset_id,
                "chunks_revectorized": revectorized_count,
                "vectors_in_index": vectors_count,
                "index_path": str(index_path),
            }
        finally:
            faiss_manager.close()

