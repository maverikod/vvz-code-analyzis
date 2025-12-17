"""
Command to check vector statistics in database.

This command provides detailed statistics about vectorized code chunks,
including total chunks, vectorized chunks, pending vectorization, and sample data.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult
from mcp_proxy_adapter.config import get_config as get_adapter_config

from ..core import CodeDatabase

logger = logging.getLogger(__name__)


class CheckVectorsCommand(Command):
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
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        schema = {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": (
                        "Root directory of the project. Database will be located at "
                        "{root_dir}/data/code_analysis.db. If not provided, will try to "
                        "find database from config or use default location."
                    ),
                },
                "project_id": {
                    "type": "string",
                    "description": (
                        "Optional project UUID to filter statistics by specific project. "
                        "If not provided, returns statistics for all projects in the database. "
                        "Format: UUID4 string (e.g., '550e8400-e29b-41d4-a716-446655440000')"
                    ),
                    "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                },
            },
            "required": [],
            "additionalProperties": False,
        }
        return schema

    async def execute(
        self,
        root_dir: Optional[str] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        """
        Execute check vectors command.

        Retrieves and returns comprehensive statistics about code chunks and their
        vectorization status from the database.

        Args:
            root_dir: Root directory of the project. Database will be at {root_dir}/data/code_analysis.db.
                     If not provided, will try to find from config or use default location.
            project_id: Optional project UUID to filter by. If provided, statistics
                       will be limited to chunks belonging to this project.
                       If None, returns statistics for all projects.

        Returns:
            SuccessResult with the following data structure:
            {
                "total_chunks": int,                    # Total number of chunks in database
                "chunks_with_vector": int,              # Chunks with vector_id (vectorized)
                "chunks_with_model": int,              # Chunks with embedding_model
                "chunks_pending_vectorization": int,   # Chunks without vector_id
                "vectorization_percentage": float,     # Percentage of vectorized chunks
                "sample_chunks": [                     # Sample of vectorized chunks (max 5)
                    {
                        "id": int,
                        "chunk_type": str,             # e.g., "DocBlock"
                        "vector_id": int,              # FAISS index ID
                        "embedding_model": str,        # Model name used
                        "source_type": str,            # 'docstring', 'comment', 'file_docstring'
                        "text_preview": str            # First 100 characters of chunk text
                    },
                    ...
                ],
                "project_id": str                      # Project ID if filtered (optional)
            }

        Raises:
            ErrorResult with code "DB_PATH_NOT_FOUND" if database path cannot be determined
            ErrorResult with code "DB_NOT_FOUND" if database file does not exist
            ErrorResult with code "CHECK_VECTORS_ERROR" for other errors
        """
        try:
            # Get database path from config or context
            db_path = None
            
            # Try to get from adapter config
            try:
                config = get_adapter_config()
                if hasattr(config, "database_path") and config.database_path:
                    db_path = Path(config.database_path)
                elif hasattr(config, "config_data"):
                    # Try to get from code_analysis config section
                    code_analysis_config = config.config_data.get("code_analysis", {})
                    if "db_path" in code_analysis_config:
                        db_path = Path(code_analysis_config["db_path"])
            except Exception as e:
                logger.debug(f"Could not get database path from config: {e}")
            
            # Try to get from root_dir parameter or context
            if not db_path:
                if root_dir:
                    db_path = Path(root_dir) / "data" / "code_analysis.db"
                else:
                    context = kwargs.get("context", {})
                    root_dir_from_context = context.get("root_dir")
                    if root_dir_from_context:
                        db_path = Path(root_dir_from_context) / "data" / "code_analysis.db"
            
            # Try to get from project_id - find project in database
            if not db_path and project_id:
                # Try common database locations
                import os
                current_dir = Path.cwd()
                possible_paths = [
                    current_dir / "data" / "code_analysis.db",
                    current_dir.parent / "data" / "code_analysis.db",
                    Path.home() / "projects" / "tools" / "code_analysis" / "data" / "code_analysis.db",
                ]
                for path in possible_paths:
                    if path.exists():
                        # Check if project exists in this database
                        try:
                            test_db = CodeDatabase(path)
                            try:
                                assert test_db.conn is not None
                                cursor = test_db.conn.cursor()
                                cursor.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
                                if cursor.fetchone():
                                    db_path = path
                                    test_db.close()
                                    break
                            finally:
                                test_db.close()
                        except Exception:
                            continue
            
            if not db_path:
                return ErrorResult(
                    message=(
                        "Database path not found. Please provide root_dir in context "
                        "or configure database_path in config. "
                        "Alternatively, provide project_id to search for database."
                    ),
                    code="DB_PATH_NOT_FOUND",
                )

            if not db_path.exists():
                return ErrorResult(
                    message=f"Database not found: {db_path}",
                    code="DB_NOT_FOUND",
                )

            database = CodeDatabase(db_path)
            
            try:
                assert database.conn is not None
                cursor = database.conn.cursor()

                # Total chunks
                cursor.execute("SELECT COUNT(*) FROM code_chunks")
                total_chunks = cursor.fetchone()[0]

                # Chunks with vector_id
                if project_id:
                    cursor.execute(
                        "SELECT COUNT(*) FROM code_chunks WHERE vector_id IS NOT NULL AND project_id = ?",
                        (project_id,),
                    )
                else:
                    cursor.execute(
                        "SELECT COUNT(*) FROM code_chunks WHERE vector_id IS NOT NULL"
                    )
                chunks_with_vector = cursor.fetchone()[0]

                # Chunks with embedding_model
                if project_id:
                    cursor.execute(
                        "SELECT COUNT(*) FROM code_chunks WHERE embedding_model IS NOT NULL AND project_id = ?",
                        (project_id,),
                    )
                else:
                    cursor.execute(
                        "SELECT COUNT(*) FROM code_chunks WHERE embedding_model IS NOT NULL"
                    )
                chunks_with_model = cursor.fetchone()[0]

                # Chunks without vector_id (pending vectorization)
                if project_id:
                    cursor.execute(
                        "SELECT COUNT(*) FROM code_chunks WHERE vector_id IS NULL AND project_id = ?",
                        (project_id,),
                    )
                else:
                    cursor.execute(
                        "SELECT COUNT(*) FROM code_chunks WHERE vector_id IS NULL"
                    )
                chunks_pending = cursor.fetchone()[0]

                # Sample chunks with vectors
                if project_id:
                    cursor.execute(
                        """
                        SELECT id, chunk_type, chunk_text, vector_id, embedding_model, source_type
                        FROM code_chunks
                        WHERE vector_id IS NOT NULL AND project_id = ?
                        LIMIT 5
                        """,
                        (project_id,),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, chunk_type, chunk_text, vector_id, embedding_model, source_type
                        FROM code_chunks
                        WHERE vector_id IS NOT NULL
                        LIMIT 5
                        """
                    )
                samples = cursor.fetchall()

                # Build sample data
                sample_data = []
                for sample in samples:
                    chunk_id, chunk_type, chunk_text, vector_id, embedding_model, source_type = sample
                    preview = chunk_text[:100] + "..." if chunk_text and len(chunk_text) > 100 else (chunk_text or "")
                    sample_data.append({
                        "id": chunk_id,
                        "chunk_type": chunk_type,
                        "vector_id": vector_id,
                        "embedding_model": embedding_model,
                        "source_type": source_type,
                        "text_preview": preview,
                    })

                result = {
                    "total_chunks": total_chunks,
                    "chunks_with_vector": chunks_with_vector,
                    "chunks_with_model": chunks_with_model,
                    "chunks_pending_vectorization": chunks_pending,
                    "vectorization_percentage": (
                        round((chunks_with_vector / total_chunks * 100), 2) if total_chunks > 0 else 0
                    ),
                    "sample_chunks": sample_data,
                }

                if project_id:
                    result["project_id"] = project_id

                return SuccessResult(data=result)

            finally:
                database.close()

        except Exception as e:
            logger.exception(f"Error during check_vectors command execution: {e}")
            return ErrorResult(
                message=f"Check vectors command failed: {str(e)}",
                code="CHECK_VECTORS_ERROR",
                details={"error": str(e)},
            )

