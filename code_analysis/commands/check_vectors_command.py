"""
Command to check vector statistics in database.

This command provides detailed statistics about vectorized code chunks,
including total chunks, vectorized chunks, pending vectorization, and sample data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand

logger = logging.getLogger(__name__)


class CheckVectorsCommand(BaseMCPCommand):
    """
    Command to check vector statistics in database.

    Provides comprehensive statistics about code chunks and their vectorization status:
    - Total number of chunks in database
    - Number of chunks ANN-indexed (FAISS: vector_id; pgvector: embedding_vec)
    - Number of chunks with embedding_model
    - Number of chunks pending ANN indexing for the active backend
    - Vectorization percentage
    - Sample chunks with vector data

    This command is useful for:
    - Monitoring vectorization progress
    - Diagnosing vectorization issues
    - Verifying ANN indexing (FAISS file index or PostgreSQL pgvector column)
    - Checking embedding model usage
    """

    name = "check_vectors"
    version = "1.0.0"
    descr = "Check vector statistics and vectorization status in database"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False  # Fast command, no need for queue

    @classmethod
    def metadata(cls: type["CheckVectorsCommand"]) -> Dict[str, Any]:
        """Extended metadata aligned with get_schema() (project_id only)."""
        from .command_metadata_helpers import (
            build_command_metadata,
            parameters_from_schema,
            simple_success_return,
        )

        return build_command_metadata(
            cls,
            detailed_description=(
                "Reports vectorization statistics for code chunks in the project: totals, "
                "ANN-ready count (FAISS vector_id or pgvector embedding_vec), pending work, "
                "percentage, and sample rows. Result includes vector_ann_backend (faiss|pgvector)."
            ),
            parameters=parameters_from_schema(cls.get_schema()),
            usage_examples=[
                {
                    "description": "Vectorization status for one project",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                    "explanation": "Uses server-configured database for the deployment.",
                },
            ],
            error_cases={
                "PROJECT_NOT_FOUND": {
                    "description": "project_id is not registered.",
                    "solution": "Call list_projects and retry.",
                },
                "CHECK_VECTORS_ERROR": {
                    "description": "Database or query failure.",
                    "solution": "Check get_database_status and server logs.",
                },
            },
            return_value=simple_success_return(
                data_fields={
                    "total_chunks": "integer",
                    "chunks_with_vector": "integer",
                    "vectorization_percentage": "float 0-100",
                    "sample_chunks": "up to 5 sample rows",
                },
                example={
                    "total_chunks": 10,
                    "chunks_with_vector": 8,
                    "vectorization_percentage": 80.0,
                },
            ),
            best_practices=[
                "Run after update_indexes and vectorization worker activity.",
                "Pair with get_worker_status when percentage is low.",
            ],
        )

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        base_props = cls._get_base_schema_properties()
        schema = {
            "type": "object",
            "properties": {
                **base_props,
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }
        return schema

    async def execute(
        self,
        project_id: str,
        **kwargs,
    ) -> SuccessResult:
        """
        Execute check vectors command.

        Retrieves and returns comprehensive statistics about code chunks and their
        vectorization status from the database.

        Args:
            project_id: Project UUID.

        Returns:
            SuccessResult with the following data structure:
            {
                "total_chunks": int,                    # Total number of chunks in database
                "chunks_with_vector": int,              # Chunks with vector_id (vectorized)
                "chunks_with_model": int,               # Chunks with embedding_model
                "chunks_pending_vectorization": int,    # Chunks without vector_id
                "vectorization_percentage": float,       # Percentage of vectorized chunks
                "sample_chunks": [                      # Sample of vectorized chunks (max 5)
                    {
                        "id": int,
                        "chunk_type": str,               # e.g., "DocBlock"
                        "vector_id": int | None,         # FAISS slot; null typical for pgvector
                        "embedding_model": str,          # Model name used
                        "source_type": str,              # 'docstring', 'comment', 'file_docstring'
                        "text_preview": str              # First 100 characters of chunk text
                    },
                    ...
                ],
                "project_id": str,                      # Project ID
                "root_dir": str                         # Resolved root directory path
            }

        Raises:
            ErrorResult with code "PROJECT_NOT_FOUND" if project_id not found in database
            ErrorResult with code "CHECK_VECTORS_ERROR" for other errors
        """
        try:
            from ..core.config import get_driver_config
            from ..core.storage_paths import load_raw_config
            from ..core.vector_search_backend import effective_vector_search_backend

            root_path = self._resolve_project_root(project_id)
            config_path = self._resolve_config_path()
            config_data = load_raw_config(config_path)
            dc = get_driver_config(config_data) or {}
            driver_type = str(dc.get("type") or "").strip().lower()
            code_analysis_config = config_data.get("code_analysis", config_data)
            vector_ann_backend = effective_vector_search_backend(
                driver_type,
                code_analysis_config.get("vector_search_backend"),
            )
            use_pgvector_ann = vector_ann_backend == "pgvector"
            ann_ready_col = (
                "embedding_vec IS NOT NULL"
                if use_pgvector_ann
                else "vector_id IS NOT NULL"
            )
            ann_pending_col = (
                "embedding_vec IS NULL" if use_pgvector_ann else "vector_id IS NULL"
            )

            db = self._open_database()
            proj_id = project_id

            try:
                # One execute_batch for all independent SELECTs (with or without project_id)
                if proj_id:
                    vec_params = (proj_id,)
                    check_ops = [
                        (
                            "SELECT COUNT(*) as count FROM code_chunks WHERE project_id = ?",
                            vec_params,
                        ),
                        (
                            f"SELECT COUNT(*) as count FROM code_chunks WHERE {ann_ready_col} AND project_id = ?",
                            vec_params,
                        ),
                        (
                            "SELECT COUNT(*) as count FROM code_chunks WHERE embedding_model IS NOT NULL AND project_id = ?",
                            vec_params,
                        ),
                        (
                            f"""SELECT COUNT(*) as count FROM code_chunks
                               WHERE {ann_pending_col} AND project_id = ?
                                 AND (vectorization_skipped IS NULL OR vectorization_skipped = 0)""",
                            vec_params,
                        ),
                        (
                            f"""
                        SELECT id, chunk_type, chunk_text, vector_id, embedding_model, source_type
                        FROM code_chunks
                        WHERE {ann_ready_col} AND project_id = ?
                        LIMIT 5
                        """,
                            vec_params,
                        ),
                    ]
                else:
                    check_ops = [
                        ("SELECT COUNT(*) as count FROM code_chunks", None),
                        (
                            f"SELECT COUNT(*) as count FROM code_chunks WHERE {ann_ready_col}",
                            None,
                        ),
                        (
                            "SELECT COUNT(*) as count FROM code_chunks WHERE embedding_model IS NOT NULL",
                            None,
                        ),
                        (
                            f"""SELECT COUNT(*) as count FROM code_chunks
                               WHERE {ann_pending_col}
                                 AND (vectorization_skipped IS NULL OR vectorization_skipped = 0)""",
                            None,
                        ),
                        (
                            f"""
                        SELECT id, chunk_type, chunk_text, vector_id, embedding_model, source_type
                        FROM code_chunks
                        WHERE {ann_ready_col}
                        LIMIT 5
                        """,
                            None,
                        ),
                    ]
                batch_results = db.execute_batch(check_ops)

                def _row0(idx: int) -> int:
                    d = (
                        batch_results[idx].get("data", [])
                        if idx < len(batch_results)
                        else []
                    )
                    return d[0]["count"] if d else 0

                def _data(idx: int) -> list:
                    return (
                        batch_results[idx].get("data", [])
                        if idx < len(batch_results)
                        else []
                    )

                total_chunks = _row0(0)
                chunks_with_vector = _row0(1)
                chunks_with_model = _row0(2)
                chunks_pending = _row0(3)
                samples = _data(4)

                # Build sample data
                sample_data = []
                for sample in samples:
                    # sample is a dict, not a tuple
                    chunk_id = sample["id"]
                    chunk_type = sample["chunk_type"]
                    chunk_text = sample["chunk_text"]
                    vector_id = sample["vector_id"]
                    embedding_model = sample["embedding_model"]
                    source_type = sample["source_type"]

                    preview = (
                        chunk_text[:100] + "..."
                        if chunk_text and len(chunk_text) > 100
                        else (chunk_text or "")
                    )
                    sample_data.append(
                        {
                            "id": chunk_id,
                            "chunk_type": chunk_type,
                            "vector_id": vector_id,
                            "embedding_model": embedding_model,
                            "source_type": source_type,
                            "text_preview": preview,
                        }
                    )

                result = {
                    "total_chunks": total_chunks,
                    "chunks_with_vector": chunks_with_vector,
                    "chunks_with_model": chunks_with_model,
                    "chunks_pending_vectorization": chunks_pending,
                    "vector_ann_backend": vector_ann_backend,
                    "vectorization_percentage": (
                        round((chunks_with_vector / total_chunks * 100), 2)
                        if total_chunks > 0
                        else 0
                    ),
                    "sample_chunks": sample_data,
                    "root_dir": str(root_path),
                }

                if proj_id:
                    result["project_id"] = proj_id

                return SuccessResult(data=result)
            finally:
                # Disconnect from database client
                db.disconnect()

        except Exception as e:
            logger.exception(f"Error during check_vectors command execution: {e}")
            return ErrorResult(
                message=f"Check vectors command failed: {str(e)}",
                code="CHECK_VECTORS_ERROR",
                details={"error": str(e)},
            )
