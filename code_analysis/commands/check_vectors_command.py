"""
Command to check vector statistics in database.

This command provides detailed statistics about vectorized code chunks,
including total chunks, vectorized chunks, pending vectorization, and sample data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from typing import Dict, Any, Optional

from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from .base_mcp_command import BaseMCPCommand

logger = logging.getLogger(__name__)


class CheckVectorsCommand(BaseMCPCommand):
    """
    Command to check vector statistics in database.

    Provides comprehensive statistics about code chunks and their vectorization status:
    - Total number of chunks in database
    - Number of chunks with vector_id (vectorized)
    - Number of chunks with embedding_model
    - Number of chunks pending vectorization (vector_id IS NULL)
    - Vectorization percentage
    - Sample chunks with vector data

    This command is useful for:
    - Monitoring vectorization progress
    - Diagnosing vectorization issues
    - Verifying that vectors are being added to FAISS index
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
        """
        Get detailed command metadata (man-page style documentation).

        Returns:
            Dictionary with comprehensive command documentation including:
            - detailed_description: Full command description
            - parameters: Detailed parameter descriptions with examples
            - usage_examples: Real-world usage examples
            - error_cases: All possible error codes and their meanings
            - return_value: Detailed return value structure
            - best_practices: Recommended usage patterns
        """
        return {
            "detailed_description": (
                "The `check_vectors` command provides a comprehensive overview of the "
                "vectorization status of code chunks stored in the database. "
                "It reports on the total number of chunks, how many have been "
                "vectorized (i.e., have a `vector_id` in the FAISS index), "
                "how many have an `embedding_model` specified, and how many are "
                "still pending vectorization. It also calculates the overall "
                "vectorization percentage and provides a sample of vectorized chunks "
                "with detailed information such as their FAISS ID, the embedding model used, "
                "chunk type, source type, and a text preview. "
                "This command is crucial for monitoring the progress and health of "
                "the vectorization pipeline, diagnosing issues, and verifying the "
                "integrity of the FAISS index."
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "The root directory path of the project OR a project UUID4 identifier. "
                        "If a valid UUID4 string is provided (e.g., '550e8400-e29b-41d4-a716-446655440000'), "
                        "the command will look up the project in the database and use its stored root_path. "
                        "If a file system path is provided (e.g., '/home/user/my_project' or './current_project'), "
                        "it will be used directly. The database will be located at "
                        "{root_dir}/data/code_analysis.db. This parameter is required."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/my_project",
                        "./current_project",
                        "550e8400-e29b-41d4-a716-446655440000",
                    ],
                },
                "project_id": {
                    "description": (
                        "Optional. A UUID4 string representing the project identifier. "
                        "If provided, the statistics will be filtered to include only "
                        "chunks belonging to this specific project. If omitted, "
                        "statistics for all projects in the database will be returned. "
                        "This parameter is useful when you want to filter results by a different "
                        "project than the one specified in `root_dir`. "
                        "Example: '550e8400-e29b-41d4-a716-446655440000'"
                    ),
                    "type": "string",
                    "required": False,
                    "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
            },
            "usage_examples": [
                {
                    "title": "Get vectorization status for entire database using project path",
                    "command": "check_vectors --root-dir /path/to/your/project",
                    "output": {
                        "total_chunks": 100,
                        "chunks_with_vector": 80,
                        "chunks_with_model": 80,
                        "chunks_pending_vectorization": 20,
                        "vectorization_percentage": 80.0,
                        "sample_chunks": [
                            {
                                "id": 1,
                                "chunk_type": "DocBlock",
                                "vector_id": 42,
                                "embedding_model": "text-embedding-ada-002",
                                "source_type": "docstring",
                                "text_preview": "This function performs...",
                            }
                        ],
                        "root_dir": "/path/to/your/project",
                    },
                },
                {
                    "title": "Get vectorization status using project UUID",
                    "command": "check_vectors --root-dir 550e8400-e29b-41d4-a716-446655440000",
                    "output": {
                        "total_chunks": 50,
                        "chunks_with_vector": 45,
                        "chunks_with_model": 45,
                        "chunks_pending_vectorization": 5,
                        "vectorization_percentage": 90.0,
                        "sample_chunks": [...],
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "root_dir": "/resolved/project/path",
                    },
                },
                {
                    "title": "Get vectorization status for a specific project with explicit project_id filter",
                    "command": "check_vectors --root-dir /path/to/project --project-id 550e8400-e29b-41d4-a716-446655440000",
                    "output": {
                        "total_chunks": 30,
                        "chunks_with_vector": 25,
                        "chunks_with_model": 25,
                        "chunks_pending_vectorization": 5,
                        "vectorization_percentage": 83.33,
                        "sample_chunks": [...],
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "root_dir": "/path/to/project",
                    },
                },
            ],
            "error_cases": {
                "MISSING_PARAMETER": {
                    "description": "Occurs when `root_dir` parameter is not provided or is empty.",
                    "resolution": "Ensure `root_dir` is provided with either a valid file system path or a UUID4 project identifier.",
                },
                "PROJECT_NOT_FOUND": {
                    "description": (
                        "Occurs in two scenarios: "
                        "1) When `root_dir` is a UUID4 but no matching project is found in the database. "
                        "2) When `project_id` parameter is provided but no matching project is found."
                    ),
                    "resolution": (
                        "Verify that the project UUID exists in the database using `list_projects` command. "
                        "Ensure the project has been indexed using `update_indexes` command."
                    ),
                },
                "CHECK_VECTORS_ERROR": {
                    "description": (
                        "A general error indicating a failure during command execution. "
                        "Common causes include: database access issues, corrupted database, "
                        "missing database file, or unexpected data format."
                    ),
                    "resolution": (
                        "Check the error details in the response. Verify database integrity using "
                        "`get_database_status`. Ensure the database file exists and is accessible. "
                        "Check server logs for detailed error information."
                    ),
                },
            },
            "return_value": {
                "type": "object",
                "properties": {
                    "total_chunks": {
                        "type": "integer",
                        "description": "Total number of code chunks in the database (or filtered by project_id if provided).",
                    },
                    "chunks_with_vector": {
                        "type": "integer",
                        "description": (
                            "Number of chunks that have been assigned a `vector_id` "
                            "(i.e., indexed in FAISS). These chunks are ready for semantic search."
                        ),
                    },
                    "chunks_with_model": {
                        "type": "integer",
                        "description": (
                            "Number of chunks that have an `embedding_model` specified. "
                            "This indicates which embedding model was used to generate the vector."
                        ),
                    },
                    "chunks_pending_vectorization": {
                        "type": "integer",
                        "description": (
                            "Number of chunks that do not yet have a `vector_id` (pending processing). "
                            "These chunks are waiting to be processed by the vectorization worker."
                        ),
                    },
                    "vectorization_percentage": {
                        "type": "number",
                        "description": (
                            "Percentage of chunks that have been vectorized (0.0-100.0). "
                            "Calculated as (chunks_with_vector / total_chunks * 100). "
                            "A value of 100.0 indicates all chunks are vectorized."
                        ),
                    },
                    "sample_chunks": {
                        "type": "array",
                        "description": (
                            "A list of up to 5 sample vectorized chunks with detailed metadata. "
                            "This provides a representative sample of what has been vectorized."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "integer",
                                    "description": "Internal chunk ID in the database.",
                                },
                                "chunk_type": {
                                    "type": "string",
                                    "description": "Type of the chunk (e.g., 'DocBlock', 'CodeBlock', 'Comment').",
                                },
                                "vector_id": {
                                    "type": "integer",
                                    "description": "FAISS index ID for the chunk's embedding vector.",
                                },
                                "embedding_model": {
                                    "type": "string",
                                    "description": "Name of the embedding model used (e.g., 'text-embedding-ada-002').",
                                },
                                "source_type": {
                                    "type": "string",
                                    "description": (
                                        "Source of the chunk: 'docstring', 'comment', 'file_docstring', etc. "
                                        "Indicates where the chunk text was extracted from."
                                    ),
                                },
                                "text_preview": {
                                    "type": "string",
                                    "description": "First 100 characters of the chunk's text content (truncated with '...' if longer).",
                                },
                            },
                        },
                    },
                    "project_id": {
                        "type": "string",
                        "description": (
                            "The project ID if the results were filtered by a specific project "
                            "(either via `root_dir` UUID or `project_id` parameter). "
                            "This field is only present when filtering by project."
                        ),
                        "optional": True,
                    },
                    "root_dir": {
                        "type": "string",
                        "description": (
                            "The resolved root directory path used for the query. "
                            "If `root_dir` was provided as a UUID, this will be the resolved path from the database. "
                            "If `root_dir` was provided as a path, this will be the normalized absolute path."
                        ),
                    },
                },
            },
            "best_practices": [
                "Always specify `root_dir` to ensure the correct database is accessed.",
                "Use UUID4 format for `root_dir` when you know the project ID but not the exact path.",
                "Use `project_id` parameter to filter results when you want statistics for a different project than the one in `root_dir`.",
                "Monitor `chunks_pending_vectorization` to identify backlogs in the vectorization pipeline.",
                "Check `embedding_model` in `sample_chunks` to verify that the expected models are being used.",
                "Use this command regularly to monitor vectorization progress, especially after large code changes.",
                "If `vectorization_percentage` is low, check the vectorization worker status using `get_worker_status`.",
            ],
        }

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
                        "vector_id": int,                # FAISS index ID
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
            root_path = self._resolve_project_root(project_id)
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
                            "SELECT COUNT(*) as count FROM code_chunks WHERE vector_id IS NOT NULL AND project_id = ?",
                            vec_params,
                        ),
                        (
                            "SELECT COUNT(*) as count FROM code_chunks WHERE embedding_model IS NOT NULL AND project_id = ?",
                            vec_params,
                        ),
                        (
                            "SELECT COUNT(*) as count FROM code_chunks WHERE vector_id IS NULL AND project_id = ?",
                            vec_params,
                        ),
                        (
                            """
                        SELECT id, chunk_type, chunk_text, vector_id, embedding_model, source_type
                        FROM code_chunks
                        WHERE vector_id IS NOT NULL AND project_id = ?
                        LIMIT 5
                        """,
                            vec_params,
                        ),
                    ]
                else:
                    check_ops = [
                        ("SELECT COUNT(*) as count FROM code_chunks", None),
                        (
                            "SELECT COUNT(*) as count FROM code_chunks WHERE vector_id IS NOT NULL",
                            None,
                        ),
                        (
                            "SELECT COUNT(*) as count FROM code_chunks WHERE embedding_model IS NOT NULL",
                            None,
                        ),
                        (
                            "SELECT COUNT(*) as count FROM code_chunks WHERE vector_id IS NULL",
                            None,
                        ),
                        (
                            """
                        SELECT id, chunk_type, chunk_text, vector_id, embedding_model, source_type
                        FROM code_chunks
                        WHERE vector_id IS NOT NULL
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
