"""
MCP command for revectorizing chunks.

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


class RevectorizeCommand(BaseMCPCommand):
    """
    Revectorize chunks (regenerate embeddings and update FAISS index).

    One index per project. Revectorizes all chunks in the project.

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
        force: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute chunk revectorization (one index per project).

        Args:
            self: Command instance.
            root_dir: Root directory of the project.
            project_id: Project UUID (must match root_dir/projectid).
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
                    # One index per project: revectorize all chunks in project
                    result = await self._revectorize_project(
                        database,
                        svo_client_manager,
                        storage_paths,
                        actual_project_id,
                        vector_dim,
                        force,
                    )

                    return SuccessResult(
                        data={
                            "project_id": actual_project_id,
                            "chunks_revectorized": result["chunks_revectorized"],
                            "vectors_in_index": result.get("vectors_in_index", 0),
                            "index_path": result.get("index_path"),
                        }
                    )
                finally:
                    await svo_client_manager.close()
            finally:
                database.disconnect()

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
                "the FAISS index. One index per project.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Validates project_id matches root_dir/projectid file\n"
                "3. Opens database connection\n"
                "4. Verifies project exists in database\n"
                "5. Loads config.json to get storage paths and vector dimension\n"
                "6. Initializes SVOClientManager for embedding generation\n"
                "7. Gets chunks that need revectorization for the project\n"
                "8. For each chunk: gets text, calls SVO for embedding, updates DB, sets vector_id to NULL\n"
                "9. Rebuilds FAISS index from updated embeddings\n"
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
                "- Index includes all chunks with valid embeddings (one index per project)\n\n"
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
                        "Used to identify project and resolve FAISS index path."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "123e4567-e89b-12d3-a456-426614174000",
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
                    "description": "Revectorize missing embeddings for project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "force": False,
                    },
                    "explanation": (
                        "Revectorizes only chunks without embeddings. "
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
                    "explanation": "Regenerates all embeddings. Useful after embedding model changes.",
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
                        "project_id": "Project UUID",
                        "chunks_revectorized": "Number of chunks revectorized",
                        "vectors_in_index": "Number of vectors in rebuilt FAISS index",
                        "index_path": "Path to FAISS index file ({faiss_dir}/{project_id}.bin)",
                    },
                    "example": {
                        "project_id": "123e4567-e89b-12d3-a456-426614174000",
                        "chunks_revectorized": 500,
                        "vectors_in_index": 5000,
                        "index_path": "/data/faiss/123e4567-e89b-12d3-a456-426614174000.bin",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, REVECTORIZE_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use force=False to only process missing embeddings (faster)",
                "Use force=True after embedding model changes",
                "Run revectorize before rebuild_faiss if embeddings are missing",
                "Monitor chunks_revectorized to track progress",
                "Check vectors_in_index to verify FAISS index was rebuilt",
                "Ensure SVO service is configured and accessible",
                "Run rebuild_faiss after revectorize to ensure index is updated",
            ],
        }

    async def _revectorize_project(
        self,
        database: Any,
        svo_client_manager: Any,
        storage_paths: Any,
        project_id: str,
        vector_dim: int,
        force: bool,
    ) -> Dict[str, Any]:
        """Revectorize chunks for a project (one index per project).

        Args:
            database: DatabaseClient instance.
            svo_client_manager: SVOClientManager instance.
            storage_paths: StoragePaths instance.
            project_id: Project UUID.
            vector_dim: Vector dimension.
            force: Force revectorization even if embeddings exist.

        Returns:
            Dictionary with revectorization statistics.
        """
        # One index per project: {faiss_dir}/{project_id}.bin
        index_path = get_faiss_index_path(storage_paths.faiss_dir, project_id)

        # Initialize FAISS manager
        faiss_manager = FaissIndexManager(
            index_path=str(index_path),
            vector_dim=vector_dim,
        )

        try:
            # Get chunks for this project that need revectorization
            # If force=True, get all chunks; otherwise get only chunks without embeddings
            if force:
                # Get all chunks for this project
                chunks = database.get_all_chunks_for_faiss_rebuild(
                    project_id=project_id
                )
            else:
                # Get only chunks without embeddings
                chunks = database.get_all_chunks_for_faiss_rebuild(
                    project_id=project_id
                )
                # Filter chunks without embeddings
                chunks = [
                    c
                    for c in chunks
                    if not c.get("embedding_vector") or not c.get("embedding_model")
                ]

            if not chunks:
                return {
                    "project_id": project_id,
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
                            database.execute(
                                """
                                UPDATE code_chunks
                                SET embedding_vector = ?, embedding_model = ?, vector_id = NULL
                                WHERE id = ?
                                """,
                                (embedding_json, embedding_model, chunk_id),
                            )

                            revectorized_count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to revectorize chunk {chunk_id}: {e}", exc_info=True
                    )

            # Rebuild FAISS index for this project
            vectors_count = await faiss_manager.rebuild_from_database(
                database,
                svo_client_manager,
                project_id=project_id,
            )

            return {
                "project_id": project_id,
                "chunks_revectorized": revectorized_count,
                "vectors_in_index": vectors_count,
                "index_path": str(index_path),
            }
        finally:
            faiss_manager.close()
