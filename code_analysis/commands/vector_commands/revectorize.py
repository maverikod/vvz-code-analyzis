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
from ...core.config import get_driver_config
from ...core.embedding_input import EmbeddingInput
from ...core.exceptions import ValidationError
from ...core.faiss_manager import FaissIndexManager
from ...core.pgvector_embedding import numpy_embedding_to_pgvector_text
from ...core.config_json import ConfigJSONDecodeError
from ...core.storage_paths import (
    get_faiss_index_path,
    load_raw_config,
    resolve_storage_paths,
)
from ...core.vector_search_backend import effective_vector_search_backend
from ...core.sql_portable import WHERE_FILES_ACTIVE_F

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
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "force": {
                    "type": "boolean",
                    "description": "Force revectorization even if embeddings exist (default: false)",
                    "default": False,
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self: "RevectorizeCommand",
        project_id: str,
        force: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute chunk revectorization (one index per project).

        Args:
            self: Command instance.
            project_id: Project UUID (from create_project or list_projects).
            force: Force revectorization even if embeddings exist.

        Returns:
            SuccessResult with revectorization statistics or ErrorResult on failure.
        """
        params: Dict[str, Any] = {
            "project_id": project_id,
            "force": force,
        }
        params.update(kwargs)
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return self._handle_error(e, "VALIDATION_ERROR", "revectorize")
        project_id = params["project_id"]
        force = bool(params.get("force", False))

        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)
            try:
                project = database.get_project(project_id)
                if not project:
                    return ErrorResult(
                        message=f"Project not found: {project_id}",
                        code="PROJECT_NOT_FOUND",
                    )

                config_path = self._resolve_config_path()
                if not config_path.exists():
                    return ErrorResult(
                        message=f"Configuration file not found: {config_path}",
                        code="CONFIG_NOT_FOUND",
                    )
                try:
                    config_dict = load_raw_config(config_path)
                except ConfigJSONDecodeError as exc:
                    return ErrorResult(
                        message=str(exc),
                        code="CONFIG_INVALID",
                    )

                storage_paths = resolve_storage_paths(
                    config_data=config_dict, config_path=config_path
                )

                # Get vector dimension
                code_analysis_config = config_dict.get("code_analysis", config_dict)
                vector_dim = int(code_analysis_config.get("vector_dim", 384))
                driver_cfg = get_driver_config(config_dict) or {}
                driver_type = str(driver_cfg.get("type") or "").strip().lower()
                ann = effective_vector_search_backend(
                    driver_type,
                    code_analysis_config.get("vector_search_backend"),
                )
                use_pgvector = ann == "pgvector"

                # Initialize SVO client manager
                from ...core.svo_client_manager import SVOClientManager

                svo_client_manager = SVOClientManager(
                    config_dict, root_dir=config_path.parent
                )
                await svo_client_manager.initialize()

                try:
                    from ...core.docs_markdown_vector_gate import (
                        docs_markdown_embeddings_disabled_by_policy,
                    )

                    ca_blk = config_dict.get("code_analysis")
                    di_blk = (
                        ca_blk.get("docs_indexing")
                        if isinstance(ca_blk, dict)
                        else None
                    )
                    omit_docs_markdown = docs_markdown_embeddings_disabled_by_policy(
                        di_blk
                    )

                    # One index per project: revectorize all chunks in project
                    result = await self._revectorize_project(
                        database,
                        svo_client_manager,
                        storage_paths,
                        project_id,
                        vector_dim,
                        force,
                        omit_docs_markdown=omit_docs_markdown,
                        use_pgvector=use_pgvector,
                    )

                    payload: Dict[str, Any] = {
                        "project_id": project_id,
                        "chunks_revectorized": result["chunks_revectorized"],
                        "vectors_in_index": result.get("vectors_in_index", 0),
                        "index_path": result.get("index_path"),
                    }
                    if result.get("vector_backend"):
                        payload["vector_backend"] = result["vector_backend"]
                    return SuccessResult(data=payload)
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
                "vector search storage: FAISS on disk (SQLite or Postgres with "
                "vector_search_backend=faiss) or pgvector in PostgreSQL when "
                "vector_search_backend resolves to pgvector.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Validates project_id matches root_dir/projectid file\n"
                "3. Opens database connection\n"
                "4. Verifies project exists in database\n"
                "5. Loads config.json to get storage paths and vector dimension\n"
                "6. Initializes SVOClientManager for embedding generation\n"
                "7. Gets chunks that need revectorization for the project\n"
                "8. For each chunk: gets text, calls SVO for embedding, updates DB, sets vector_id to NULL\n"
                "9. Rebuilds FAISS index from updated embeddings, or writes embedding_vec on Postgres\n"
                "10. Returns revectorization statistics\n\n"
                "Revectorization Process:\n"
                "- Finds chunks without embeddings or with force=True (all chunks)\n"
                "- Generates new embeddings using SVO (Semantic Vector Operations) service\n"
                "- Updates code_chunks.embedding_vector in database\n"
                "- Updates code_chunks.embedding_model with model name\n"
                "- Sets vector_id to NULL; with pgvector also sets embedding_vec from the new embedding\n"
                "- Rebuilds FAISS index after revectorization when using FAISS; optional REINDEX HNSW for pgvector\n\n"
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
                "Run revectorize before rebuild_faiss if embeddings are missing (FAISS mode)",
                "Monitor chunks_revectorized to track progress",
                "Check vectors_in_index to verify FAISS index was rebuilt (FAISS mode)",
                "With pgvector, success payload includes vector_backend=pgvector and index_path=null",
                "Ensure SVO service is configured and accessible",
                "Run rebuild_faiss after revectorize to resync pgvector from JSON if needed",
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
        *,
        omit_docs_markdown: bool = False,
        use_pgvector: bool = False,
    ) -> Dict[str, Any]:
        """Revectorize chunks for a project (one index per project).

        Args:
            database: DatabaseClient instance.
            svo_client_manager: SVOClientManager instance.
            storage_paths: StoragePaths instance.
            project_id: Project UUID.
            vector_dim: Vector dimension.
            force: Force revectorization even if embeddings exist.
            omit_docs_markdown: Skip ``docs_markdown`` chunks when policy disables doc vectors.
            use_pgvector: When True, skip FAISS and write pgvector column on Postgres.

        Returns:
            Dictionary with revectorization statistics.
        """
        index_path = None
        faiss_manager = None
        if not use_pgvector:
            # One index per project: {faiss_dir}/{project_id}.bin
            index_path = get_faiss_index_path(storage_paths.faiss_dir, project_id)
            faiss_manager = FaissIndexManager(
                index_path=str(index_path),
                vector_dim=vector_dim,
            )

        try:
            # Fetch chunks through the universal driver chain (Command -> universal
            # driver -> specific driver -> DBMS) so this works on both SQLite and
            # Postgres. ``?`` placeholders are translated per backend by the driver.
            fetch_result = database.execute(
                f"""
                SELECT cc.id, cc.chunk_text, cc.embedding_vector,
                       cc.embedding_model, cc.source_type
                FROM code_chunks cc
                INNER JOIN files f ON cc.file_id = f.id
                WHERE cc.project_id = ?
                  AND {WHERE_FILES_ACTIVE_F}
                ORDER BY cc.created_at DESC, cc.id DESC
                """,
                (project_id,),
            )
            chunks = (
                fetch_result.get("data", [])
                if isinstance(fetch_result, dict)
                else (fetch_result or [])
            )
            if not force:
                # Only chunks that still lack an embedding.
                chunks = [
                    c
                    for c in chunks
                    if not c.get("embedding_vector") or not c.get("embedding_model")
                ]

            if omit_docs_markdown:
                from ...core.docs_markdown_vector_gate import is_docs_markdown_chunk

                chunks = [c for c in chunks if not is_docs_markdown_chunk(chunk=c)]

            if not chunks:
                return {
                    "project_id": project_id,
                    "chunks_revectorized": 0,
                    "index_path": None if use_pgvector else str(index_path),
                    "vector_backend": "pgvector" if use_pgvector else "faiss",
                }

            # Revectorize chunks in BATCHES: one embed call per batch (not per
            # chunk). Per-chunk round-trips through the queued embed path are
            # ~seconds each and on a large project overrun the sync-cap; batching
            # keeps the whole command well under it.
            import json
            import numpy as np

            is_pg = (
                use_pgvector and getattr(database, "_driver_type", None) == "postgres"
            )
            pending = [
                EmbeddingInput(text=c.get("chunk_text", ""), id=c.get("id"))
                for c in chunks
                if c.get("chunk_text")
            ]

            revectorized_count = 0
            # Each batch = one in-process embed_execute call (see
            # SVOClientManager.get_embeddings), so batches can be large.
            batch_size = 128
            for start in range(0, len(pending), batch_size):
                batch = pending[start : start + batch_size]
                try:
                    embedded = await svo_client_manager.get_embeddings(batch)
                except Exception as e:
                    logger.warning(
                        "Failed to embed revectorize batch [%d:%d]: %s",
                        start,
                        start + len(batch),
                        e,
                        exc_info=True,
                    )
                    continue

                got = sum(
                    1
                    for t in (embedded or [])
                    if getattr(t, "embedding", None) is not None
                )
                logger.info(
                    "[REVEC] batch [%d:%d] embeddings_returned=%d/%d",
                    start,
                    start + len(batch),
                    got,
                    len(batch),
                )
                for tmp in embedded or []:
                    embedding = getattr(tmp, "embedding", None)
                    if embedding is None:
                        continue
                    chunk_id = getattr(tmp, "id", None)
                    embedding_model = getattr(tmp, "embedding_model", None)
                    try:
                        embedding_array = np.array(embedding, dtype="float32")
                        embedding_json = json.dumps(embedding_array.tolist())

                        # Postgres + pgvector: store normalized vector in embedding_vec
                        if is_pg:
                            norm = FaissIndexManager._normalize_vector(embedding_array)
                            vt = numpy_embedding_to_pgvector_text(norm)
                            database.execute(
                                """
                                UPDATE code_chunks
                                SET embedding_vector = ?,
                                    embedding_model = ?,
                                    vector_id = NULL,
                                    embedding_vec = ?::vector
                                WHERE id = ?
                                """,
                                (embedding_json, embedding_model, vt, chunk_id),
                            )
                        else:
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
                            "Failed to write revectorized chunk %s: %s",
                            chunk_id,
                            e,
                            exc_info=True,
                        )

            if use_pgvector:
                try:
                    database.execute("REINDEX INDEX idx_code_chunks_embedding_vec_hnsw")
                except Exception as re_ix_e:
                    logger.warning(
                        "REINDEX idx_code_chunks_embedding_vec_hnsw skipped: %s",
                        re_ix_e,
                    )
                return {
                    "project_id": project_id,
                    "chunks_revectorized": revectorized_count,
                    "vectors_in_index": revectorized_count,
                    "index_path": None,
                    "vector_backend": "pgvector",
                }

            assert faiss_manager is not None
            # Rebuild FAISS index for this project
            vectors_count = await faiss_manager.rebuild_from_database(
                database,
                svo_client_manager,
                project_id=project_id,
                omit_docs_markdown=omit_docs_markdown,
            )

            return {
                "project_id": project_id,
                "chunks_revectorized": revectorized_count,
                "vectors_in_index": vectors_count,
                "index_path": str(index_path),
                "vector_backend": "faiss",
            }
        finally:
            if faiss_manager is not None:
                faiss_manager.close()
