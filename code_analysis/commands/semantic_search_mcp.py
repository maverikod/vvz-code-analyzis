"""
MCP command wrapper for semantic search.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand
from ..core.config import get_driver_config
from ..core.exceptions import ValidationError
from ..core.faiss_manager import FaissIndexManager
from ..core.pgvector_embedding import numpy_embedding_to_pgvector_text
from ..core.config_json import ConfigJSONDecodeError
from ..core.embedding_input import EmbeddingInput
from ..core.storage_paths import (
    get_faiss_index_path,
    load_raw_config,
    resolve_storage_paths,
)
from ..core.vector_search_backend import (
    driver_requires_faiss,
    effective_vector_search_backend,
)

logger = logging.getLogger(__name__)


def _omit_semantic_hit_for_docs_markdown(
    source_type: Optional[Any],
    *,
    docs_markdown_vectorize_enabled: bool,
) -> bool:
    """When ``docs_indexing.vectorize`` is false, drop ``docs_markdown`` chunk hits (defense in depth)."""
    if docs_markdown_vectorize_enabled:
        return False
    return str(source_type or "") == "docs_markdown"


class SemanticSearchMCPCommand(BaseMCPCommand):
    """Perform semantic search using embeddings and a FAISS index.

    This MCP command requires real embedding service to be available.
    No fallback mechanisms - raises exception if service is unavailable.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Human readable description.
        category: Command category.
        author: Author name.
        email: Author email.
        use_queue: Whether command runs via queue.
    """

    name = "semantic_search"
    version = "1.0.0"
    descr = "Perform semantic search using embeddings and FAISS vectors"
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["SemanticSearchMCPCommand"]) -> Dict[str, Any]:
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
                "query": {
                    "type": "string",
                    "description": "Search query text",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Maximum FAISS neighbors to retrieve (1–100). Default 10. "
                        "Values outside the range are rejected. Same parameter name as "
                        "fulltext_search / search_ast_nodes."
                    ),
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
                "min_score": {
                    "type": "number",
                    "description": (
                        "Optional minimum similarity score threshold (0.0–1.0). "
                        "Values outside the range are rejected."
                    ),
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
            },
            "required": ["project_id", "query"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Reject ``limit`` and ``min_score`` outside schema bounds after schema validation."""
        params = super().validate_params(params)
        schema = self.get_schema()
        props = schema.get("properties") or {}
        for key in ("limit", "min_score"):
            if key not in params or params[key] is None:
                continue
            value = params[key]
            prop = props.get(key) or {}
            minimum = prop.get("minimum")
            maximum = prop.get("maximum")
            if minimum is not None and value < minimum:
                raise ValidationError(
                    f"{self.name}: parameter {key!r} must be >= {minimum}, got {value!r}",
                    field=key,
                    details={"minimum": minimum, "maximum": maximum},
                )
            if maximum is not None and value > maximum:
                raise ValidationError(
                    f"{self.name}: parameter {key!r} must be <= {maximum}, got {value!r}",
                    field=key,
                    details={"minimum": minimum, "maximum": maximum},
                )
        return params

    async def execute(
        self: "SemanticSearchMCPCommand",
        project_id: str,
        query: str,
        limit: int = 10,
        min_score: Optional[float] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """Execute semantic search.

        Args:
            self: Command instance.
            project_id: Project UUID (from create_project or list_projects).
            query: Search query text.
            limit: Maximum number of results to return (same semantics as fulltext_search limit).
            min_score: Optional minimum similarity score threshold.

        Returns:
            SuccessResult with search results or ErrorResult on failure.
        """
        params: Dict[str, Any] = {
            "project_id": project_id,
            "query": query,
            "limit": limit,
            "min_score": min_score,
        }
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return self._handle_error(e, "VALIDATION_ERROR", "semantic_search")
        project_id = params["project_id"]
        query = params["query"]
        limit = int(params.get("limit", 10))
        min_score = params.get("min_score")

        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)
            try:
                config_path = self._resolve_config_path()
                if not config_path.exists():
                    return ErrorResult(
                        message=f"Server configuration file not found: {config_path}",
                        code="CONFIG_NOT_FOUND",
                    )
                try:
                    config_dict = load_raw_config(config_path)
                except ConfigJSONDecodeError as exc:
                    return ErrorResult(
                        message=str(exc),
                        code="CONFIG_INVALID",
                    )

                # Extract code_analysis config (may be nested)
                code_analysis_config = config_dict.get("code_analysis", config_dict)
                vector_dim = int(code_analysis_config.get("vector_dim", 384))

                driver_cfg = get_driver_config(config_dict) or {}
                driver_type = str(driver_cfg.get("type") or "").strip().lower()
                configured_vsb = code_analysis_config.get("vector_search_backend")
                if driver_requires_faiss(driver_type) and (
                    str(configured_vsb or "").strip().lower() == "pgvector"
                ):
                    logger.warning(
                        "vector_search_backend=pgvector is invalid for driver %s; "
                        "FAISS is always used (config validator should reject this combination)",
                        driver_type,
                    )
                ann_backend = effective_vector_search_backend(
                    driver_type, configured_vsb
                )
                logger.debug(
                    "semantic_search ANN backend effective=%s driver=%s",
                    ann_backend,
                    driver_type,
                )

                raw_docs_indexing = code_analysis_config.get("docs_indexing")
                docs_di = (
                    raw_docs_indexing if isinstance(raw_docs_indexing, dict) else {}
                )
                docs_markdown_vectorize_enabled = bool(docs_di.get("vectorize"))

                if ann_backend == "pgvector":
                    from ..core.svo_client_manager import SVOClientManager

                    import numpy as np

                    config_root = config_path.parent
                    svo_pg = SVOClientManager(config_dict, root_dir=config_root)
                    await svo_pg.initialize()
                    try:

                        q_emb = await svo_pg.get_embeddings(
                            [EmbeddingInput(text=query)]
                        )
                        if not q_emb or getattr(q_emb[0], "embedding", None) is None:
                            return ErrorResult(
                                message="Failed to get embedding for query from real service",
                                code="EMBEDDING_SERVICE_ERROR",
                            )
                        qv = np.array(getattr(q_emb[0], "embedding"), dtype="float32")
                        n = float(np.linalg.norm(qv))
                        if n <= 0:
                            return ErrorResult(
                                message="Invalid embedding vector (zero norm)",
                                code="EMBEDDING_SERVICE_ERROR",
                            )
                        query_vec = qv / n
                    finally:
                        await svo_pg.close()

                    cnt_pg = database.execute(
                        """
                        SELECT COUNT(*) AS c FROM code_chunks
                        WHERE project_id = ?
                          AND embedding_vec IS NOT NULL
                        """,
                        (project_id,),
                    )
                    cr = (cnt_pg.get("data") or [{}])[0]
                    n_pg = int(cr.get("c") or cr.get("C") or 0)
                    if n_pg <= 0:
                        return ErrorResult(
                            message=(
                                "No rows with embedding_vec for this project. "
                                "Run vectorization worker or rebuild_faiss (pgvector sync)."
                            ),
                            code="PGVECTOR_INDEX_EMPTY",
                            details={"project_id": project_id},
                        )

                    qtxt = numpy_embedding_to_pgvector_text(query_vec)
                    pq = database.execute(
                        """
                        SELECT
                            c.id AS chunk_id,
                            c.file_id,
                            c.vector_id,
                            c.chunk_uuid,
                            c.chunk_type,
                            c.chunk_text,
                            c.line,
                            c.source_type,
                            f.path AS file_path,
                            c.bm25_score,
                            c.token_count,
                            (c.embedding_vec <=> ?::vector) AS dist
                        FROM code_chunks c
                        JOIN files f ON f.id = c.file_id
                        WHERE c.project_id = ?
                          AND c.embedding_vec IS NOT NULL
                        ORDER BY c.embedding_vec <=> ?::vector
                        LIMIT ?
                        """,
                        (qtxt, project_id, qtxt, int(limit)),
                    )
                    prow = pq.get("data", []) if isinstance(pq, dict) else []
                    results_pg: list[dict[str, Any]] = []
                    for row in prow:
                        dist = float(row.get("dist") or 0.0)
                        score = 1.0 / (1.0 + dist)
                        if min_score is not None and score < float(min_score):
                            continue
                        if _omit_semantic_hit_for_docs_markdown(
                            row.get("source_type"),
                            docs_markdown_vectorize_enabled=docs_markdown_vectorize_enabled,
                        ):
                            continue
                        item_pg: dict[str, Any] = {
                            "score": score,
                            "distance": dist,
                            "vector_id": row.get("vector_id"),
                            "chunk_id": row.get("chunk_id"),
                            "file_id": row.get("file_id"),
                            "chunk_uuid": row.get("chunk_uuid"),
                            "chunk_type": row.get("chunk_type"),
                            "file_path": row.get("file_path"),
                            "line": row.get("line"),
                            "text": row.get("chunk_text"),
                            "vector_backend": "pgvector",
                        }
                        if row.get("bm25_score") is not None:
                            item_pg["bm25_score"] = float(row["bm25_score"])
                        if row.get("token_count") is not None:
                            item_pg["token_count"] = int(row["token_count"])
                        results_pg.append(item_pg)

                    return SuccessResult(
                        data={
                            "query": query,
                            "limit": int(limit),
                            "min_score": min_score,
                            "index_path": None,
                            "vector_backend": "pgvector",
                            "project_id": project_id,
                            "results": results_pg,
                            "count": len(results_pg),
                        }
                    )

                # Resolve storage paths (one index per project)
                storage_paths = resolve_storage_paths(
                    config_data=config_dict, config_path=config_path
                )

                # One index per project: {faiss_dir}/{project_id}.bin
                index_path = get_faiss_index_path(storage_paths.faiss_dir, project_id)
                missing_index_file = not index_path.exists()

                if missing_index_file:
                    count_res = database.execute(
                        """
                        SELECT COUNT(*) AS c FROM code_chunks
                        WHERE project_id = ?
                          AND embedding_model IS NOT NULL
                          AND embedding_vector IS NOT NULL
                        """,
                        (project_id,),
                    )
                    rows = count_res.get("data") or []
                    emb_row = rows[0] if rows else {}
                    emb_count = int(emb_row.get("c") or emb_row.get("C") or 0)
                    if emb_count == 0:
                        return ErrorResult(
                            message=(
                                "FAISS index file not found and no embedded chunks in the "
                                "database for this project. Run vectorization / indexing first."
                            ),
                            code="FAISS_INDEX_NOT_FOUND",
                            details={
                                "index_path": str(index_path),
                                "project_id": project_id,
                            },
                        )

                try:
                    faiss_manager = FaissIndexManager(
                        index_path=str(index_path),
                        vector_dim=vector_dim,
                    )
                    if not missing_index_file:
                        faiss_manager._load_index()
                except ImportError as e:
                    return SuccessResult(
                        data={
                            "query": query,
                            "results": [],
                            "count": 0,
                            "warning": "FAISS is not installed; returning empty results",
                            "details": {"error": str(e), "index_path": str(index_path)},
                        }
                    )

                # Get query embedding using real embedding service
                from ..core.svo_client_manager import SVOClientManager

                # Config and cert paths in config are relative to config file directory (server root)
                config_root = config_path.parent
                svo_client_manager = SVOClientManager(config_dict, root_dir=config_root)
                await svo_client_manager.initialize()

                try:
                    if missing_index_file:
                        from ...core.docs_markdown_vector_gate import (
                            docs_markdown_embeddings_disabled_by_policy,
                        )

                        ca_blk = config_dict.get("code_analysis")
                        di_blk = (
                            ca_blk.get("docs_indexing")
                            if isinstance(ca_blk, dict)
                            else None
                        )
                        omit_md_search = docs_markdown_embeddings_disabled_by_policy(
                            di_blk
                        )
                        logger.info(
                            "FAISS index file missing at %s; rebuilding from database "
                            "for project %s",
                            index_path,
                            project_id,
                        )
                        loaded = await faiss_manager.rebuild_from_database(
                            database,
                            svo_client_manager,
                            project_id=project_id,
                            omit_docs_markdown=omit_md_search,
                        )
                        if loaded <= 0:
                            return ErrorResult(
                                message=(
                                    "FAISS index file was missing; rebuild from database "
                                    "loaded no vectors."
                                ),
                                code="FAISS_INDEX_NOT_FOUND",
                                details={
                                    "index_path": str(index_path),
                                    "project_id": project_id,
                                },
                            )

                    # Create query embedding input
                    query_chunk = EmbeddingInput(text=query)
                    chunks_with_emb = await svo_client_manager.get_embeddings(
                        [query_chunk]
                    )

                    if (
                        not chunks_with_emb
                        or getattr(chunks_with_emb[0], "embedding", None) is None
                    ):
                        error_msg = (
                            "Failed to get embedding for query from real service"
                        )
                        logger.error(
                            "%s: chunks_with_emb=%s, has_embedding=%s",
                            error_msg,
                            chunks_with_emb is not None,
                            (
                                hasattr(chunks_with_emb[0], "embedding")
                                if chunks_with_emb
                                else False
                            ),
                        )
                        return ErrorResult(
                            message=error_msg,
                            code="EMBEDDING_SERVICE_ERROR",
                        )

                    # Use real embedding
                    import numpy as np

                    embedding = getattr(chunks_with_emb[0], "embedding")
                    query_vec = np.array(embedding, dtype="float32")
                    norm = float(np.linalg.norm(query_vec))
                    if norm > 0:
                        query_vec = query_vec / norm
                    else:
                        error_msg = "Invalid embedding vector (zero norm)"
                        logger.error(
                            "%s: embedding vector has zero norm (dim=%d)",
                            error_msg,
                            len(query_vec),
                        )
                        return ErrorResult(
                            message=error_msg,
                            code="EMBEDDING_SERVICE_ERROR",
                        )
                finally:
                    await svo_client_manager.close()

                distances, vector_ids = faiss_manager.search(query_vec, k=int(limit))

                ids: list[int] = (
                    [int(i) for i in vector_ids.tolist()]
                    if hasattr(vector_ids, "tolist")
                    else []
                )
                if not ids:
                    return SuccessResult(
                        data={
                            "query": query,
                            "results": [],
                            "count": 0,
                            "index_path": str(index_path),
                        }
                    )

                # Resolve chunk metadata by project_id (one index per project)
                placeholders = ",".join(["?"] * len(ids))
                result = database.execute(
                    f"""
                    SELECT
                        c.id AS chunk_id,
                        c.file_id,
                        c.vector_id,
                        c.chunk_uuid,
                        c.chunk_type,
                        c.chunk_text,
                        c.line,
                        c.source_type,
                        f.path AS file_path,
                        c.bm25_score,
                        c.token_count
                    FROM code_chunks c
                    JOIN files f ON f.id = c.file_id
                    WHERE c.project_id = ?
                      AND c.vector_id IN ({placeholders})
                    """,
                    [project_id, *ids],
                )
                rows = result.get("data", [])
                by_vector_id: dict[int, dict[str, Any]] = {
                    int(r["vector_id"]): dict(r) for r in rows
                }

                results: list[dict[str, Any]] = []
                for dist, vid in zip(distances.tolist(), ids):
                    score = 1.0 / (1.0 + float(dist))
                    if min_score is not None and score < float(min_score):
                        continue
                    row = by_vector_id.get(int(vid))
                    if not row:
                        continue
                    if _omit_semantic_hit_for_docs_markdown(
                        row.get("source_type"),
                        docs_markdown_vectorize_enabled=docs_markdown_vectorize_enabled,
                    ):
                        continue
                    item: dict[str, Any] = {
                        "score": score,
                        "distance": float(dist),
                        "vector_id": int(vid),
                        "chunk_id": row.get("chunk_id"),
                        "file_id": row.get("file_id"),
                        "chunk_uuid": row.get("chunk_uuid"),
                        "chunk_type": row.get("chunk_type"),
                        "file_path": row.get("file_path"),
                        "line": row.get("line"),
                        "text": row.get("chunk_text"),
                    }
                    if row.get("bm25_score") is not None:
                        item["bm25_score"] = float(row["bm25_score"])
                    if row.get("token_count") is not None:
                        item["token_count"] = int(row["token_count"])
                    results.append(item)

                return SuccessResult(
                    data={
                        "query": query,
                        "limit": int(limit),
                        "min_score": min_score,
                        "index_path": str(index_path),
                        "project_id": project_id,
                        "results": results,
                        "count": len(results),
                    }
                )

            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "SEARCH_ERROR", "semantic_search")

    @classmethod
    def metadata(cls: type["SemanticSearchMCPCommand"]) -> Dict[str, Any]:
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
                "The semantic_search command performs semantic search using embeddings and a "
                "FAISS vector index. It converts the query text to an embedding via the "
                "configured embedding service, then searches for similar code chunks in the "
                "per-project index.\n\n"
                "Operation flow:\n"
                "1. Resolves the project root from required ``project_id``\n"
                "2. Opens the shared database client\n"
                "3. Loads server config (vector_dim, embedding service, storage paths)\n"
                "4. Resolves FAISS index path (one file per project: {faiss_dir}/{project_id}.bin)\n"
                "5. Loads the FAISS index, or rebuilds it from the database if the file is "
                "missing and embedded chunks exist (FaissIndexManager)\n"
                "6. Obtains and L2-normalizes the query embedding (SVOClientManager)\n"
                "7. Runs FAISS search for up to ``limit`` neighbors (1–100, default 10; out-of-range rejected)\n"
                "8. Loads chunk metadata from SQLite and applies optional ``min_score`` filter\n"
                "9. Returns ranked results with similarity scores\n\n"
                "Semantic search:\n"
                "- Embedding-based similarity, not keyword FTS\n"
                "- Similarity score: 1.0 / (1.0 + distance)\n\n"
                "FAISS index:\n"
                "- One index per project under configured ``faiss_dir``\n"
                "- If the ``.bin`` file is missing but ``code_chunks`` has embeddings for the "
                "project, the command rebuilds the index from the database before searching\n\n"
                "Important notes:\n"
                "- Requires a working embedding service\n"
                "- Requires FAISS (optional dependency); missing FAISS may yield empty results with a warning\n"
                "- ``limit`` must be 1–100; out-of-range values are rejected in ``validate_params``\n"
                "- ``min_score`` must be 0.0–1.0 when set; filters by similarity threshold"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Project UUID (from ``create_project`` or ``list_projects``). Required; "
                        "selects the FAISS index file and DB rows for this project."
                    ),
                    "type": "string",
                    "required": True,
                },
                "query": {
                    "description": (
                        "Search query text. Converted to an embedding vector; used to query FAISS."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "database connection",
                        "file processing",
                        "error handling",
                        "authentication logic",
                    ],
                },
                "limit": {
                    "description": (
                        "Maximum number of FAISS neighbors (1–100). Default 10. Out-of-range "
                        "values are rejected. Same parameter name as ``fulltext_search`` and "
                        "``search_ast_nodes``."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
                "min_score": {
                    "description": (
                        "Optional minimum similarity score threshold (0.0–1.0). "
                        "Only results with score >= min_score are returned. "
                        "Score is calculated as 1.0 / (1.0 + distance)."
                    ),
                    "type": "number",
                    "required": False,
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "examples": [0.5, 0.7, 0.9],
                },
            },
            "usage_examples": [
                {
                    "description": "Basic semantic search",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "query": "database connection",
                        "limit": 10,
                    },
                    "explanation": (
                        "Searches for code chunks semantically similar to 'database connection', "
                        "returning up to 10 results."
                    ),
                },
                {
                    "description": "Search with minimum score threshold",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "query": "error handling",
                        "limit": 20,
                        "min_score": 0.7,
                    },
                    "explanation": (
                        "Searches for similar code with minimum similarity score of 0.7, "
                        "returning up to 20 results."
                    ),
                },
                {
                    "description": "Find highly similar code",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "query": "file processing",
                        "limit": 5,
                        "min_score": 0.9,
                    },
                    "explanation": (
                        "Finds highly similar code (score >= 0.9) related to 'file processing', "
                        "returning up to 5 results."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "Unknown ``project_id`` or project root missing from registration",
                    "solution": "Use ``list_projects`` and a valid UUID. Run ``update_indexes`` first.",
                },
                "CONFIG_NOT_FOUND": {
                    "description": "Configuration file not found",
                    "example": "Server config.json missing",
                    "solution": "Ensure server config has embedding service configuration (code_analysis.embedding).",
                },
                "FAISS_INDEX_NOT_FOUND": {
                    "description": "FAISS index not found",
                    "example": "Index file doesn't exist for project",
                    "solution": (
                        "Run update_indexes first to build the FAISS index. "
                        "One index per project: {faiss_dir}/{project_id}.bin"
                    ),
                },
                "EMBEDDING_SERVICE_ERROR": {
                    "description": "Failed to get embedding from service",
                    "example": "Service unavailable, invalid response, or zero norm vector",
                    "solution": (
                        "Check embedding service configuration in server config. "
                        "Ensure service is available and responding correctly."
                    ),
                },
                "SEARCH_ERROR": {
                    "description": "General error during search",
                    "example": "Database error, FAISS error, or vector dimension mismatch",
                    "solution": (
                        "Check database integrity, verify FAISS index is valid, "
                        "ensure vector_dim matches index configuration."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "query": "Search query that was used",
                        "limit": "Maximum number of results requested (same as request parameter)",
                        "min_score": "Minimum score threshold (if provided)",
                        "index_path": "Path to FAISS index file ({faiss_dir}/{project_id}.bin)",
                        "project_id": "Project UUID",
                        "results": (
                            "List of similar code chunks. Each contains:\n"
                            "- score: Similarity score (0.0-1.0, higher is better)\n"
                            "- distance: Distance in vector space (lower is better)\n"
                            "- vector_id: Integer position in the FAISS index (not a DB primary key)\n"
                            "- chunk_id: code_chunks.id (UUID string after DB UUID migration)\n"
                            "- file_id: files.id for the chunk (UUID string after migration)\n"
                            "- chunk_uuid: Stable chunk business key (string; distinct from chunk_id)\n"
                            "- chunk_type: Type of chunk\n"
                            "- file_path: Path to file containing the chunk\n"
                            "- line: Line number in file\n"
                            "- text: Text content of chunk"
                        ),
                        "count": "Number of results returned (after min_score filtering)",
                    },
                    "example": {
                        "query": "database connection",
                        "limit": 10,
                        "min_score": None,
                        "index_path": "data/faiss/928bcf10-db1c-47a3-8341-f60a6d997fe7.bin",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "results": [
                            {
                                "score": 0.85,
                                "distance": 0.176,
                                "vector_id": 42,
                                "chunk_id": "c3d4e5f6-a7b8-4901-c234-567890123456",
                                "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                                "chunk_uuid": "9f8e7d6c-5b4a-4321-8fed-cba987654321",
                                "chunk_type": "function",
                                "file_path": "src/db.py",
                                "line": 10,
                                "text": "def connect_to_database(...)",
                            },
                        ],
                        "count": 1,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": (
                        "Error code (e.g., PROJECT_NOT_FOUND, CONFIG_NOT_FOUND, "
                        "FAISS_INDEX_NOT_FOUND, EMBEDDING_SERVICE_ERROR, SEARCH_ERROR)"
                    ),
                    "message": "Human-readable error message",
                    "details": "Additional error details (if available)",
                },
            },
            "best_practices": [
                "Run update_indexes first to build the FAISS index",
                "Ensure embedding service is configured and available",
                "Use min_score to filter low-quality results",
                "Adjust limit based on expected result count",
                "Similarity scores help identify most relevant matches",
                "Query text should describe the concept you're searching for",
            ],
        }
