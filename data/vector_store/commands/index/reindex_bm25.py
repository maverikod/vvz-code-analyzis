"""
Reindex BM25 command for indexing all existing chunks.

This command reindexes all existing chunks in the vector store for BM25 search.
It iterates through all chunks and indexes them for BM25 search functionality.
"""

import logging
from typing import Dict, Any, Optional, Union

from vector_store.exceptions import CommandError
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from vector_store.commands.base import BaseVectorStoreCommand

logger = logging.getLogger(__name__)


class ReindexBM25Command(BaseVectorStoreCommand):
    """
    Reindex BM25 command for indexing all existing chunks.

    This command reindexes all existing chunks in the vector store for BM25 search.
    It iterates through all chunks and indexes them for BM25 search functionality.

    Parameters:
        batch_size (integer, optional): Number of chunks to process in each batch (default: 100)
        force (boolean, optional): Force reindexing even if BM25 index already exists (default: false)

    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "indexed_count": 150,
                    "failed_count": 0,
                    "total_chunks": 150,
                    "indexing_time": 2.5
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "reindex_error",
                    "message": "Failed to reindex chunks for BM25",
                    "data": {"indexed_count": 50, "failed_count": 5}
                }
            }

    Error codes:
        | Code              | Description                    | When
        |-------------------|--------------------------------|-------------------
        | bm25_not_available| BM25 service not available     | When BM25 service is not configured
        | reindex_error     | Reindexing failed              | When reindexing operation fails
        | invalid_params    | Invalid parameters provided    | When parameters are invalid

    Examples:
        Success:
            {
                "success": true,
                "data": {
                    "indexed_count": 150,
                    "failed_count": 0,
                    "total_chunks": 150,
                    "indexing_time": 2.5
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "bm25_not_available",
                    "message": "BM25 service is not configured"
                }
            }
    """

    name = "reindex_bm25"
    result_class = SuccessResult

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for reindex BM25 command parameters.

        Returns:
            dict: JSON schema with parameter definitions and validation rules
        """
        return {
            "type": "object",
            "properties": {
                "batch_size": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 100,
                    "description": "Number of chunks to process in each batch"
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force reindexing even if BM25 index already exists"
                }
            },
            "additionalProperties": False
        }

    @classmethod
    def get_result_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for command result.

        Returns:
            JSON schema for result
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "indexed_count": {"type": "integer", "minimum": 0},
                        "failed_count": {"type": "integer", "minimum": 0},
                        "total_chunks": {"type": "integer", "minimum": 0},
                        "indexing_time": {"type": "number", "minimum": 0.0}
                    },
                    "required": ["indexed_count", "failed_count", "total_chunks", "indexing_time"]
                }
            },
            "required": ["success", "data"]
        }

    @classmethod
    def get_error_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for error responses.

        Returns:
            JSON schema for errors
        """
        return super().get_error_schema([
            "bm25_not_available", "reindex_error", "invalid_params"
        ])

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.

        Returns:
            Dictionary with command metadata
        """
        error_codes = [
            {"code": "bm25_not_available", "description": "BM25 service not available", "when": "When BM25 service is not configured"},
            {"code": "reindex_error", "description": "Reindexing failed", "when": "When reindexing operation fails"},
            {"code": "invalid_params", "description": "Invalid parameters provided", "when": "When parameters are invalid"}
        ]
        
        examples = {
            "success": {
                "success": True,
                "data": {
                    "indexed_count": 150,
                    "failed_count": 0,
                    "total_chunks": 150,
                    "indexing_time": 2.5
                }
            },
            "error": {
                "success": False,
                "error": {
                    "code": "bm25_not_available",
                    "message": "BM25 service is not configured"
                }
            }
        }
        
        return super().get_metadata(error_codes, examples)

    async def execute(
        self,
        batch_size: Optional[int] = None,
        force: Optional[bool] = None,
        **params
    ) -> Union[SuccessResult, ErrorResult]:
        """
        Execute reindex BM25 command.

        Args:
            batch_size: Number of chunks to process in each batch
            force: Force reindexing even if BM25 index already exists
            **params: Additional parameters

        Returns:
            SuccessResult with reindexing statistics or ErrorResult on error
        """
        import time
        
        try:
            # Set defaults
            if batch_size is None:
                batch_size = 100
            if force is None:
                force = False

            # Validate parameters
            if batch_size < 1 or batch_size > 1000:
                return ErrorResult(
                    code="invalid_params",
                    message="batch_size must be between 1 and 1000",
                    details={"batch_size": batch_size}
                )

            # Check if BM25 service is available
            if not self.vector_store_service.bm25_service:
                return ErrorResult(
                    code="bm25_not_available",
                    message="BM25 service is not configured",
                    details={"available_services": ["crud", "filter", "faiss"]}
                )

            start_time = time.time()
            logger.info(f"Starting BM25 reindexing with batch_size={batch_size}, force={force}")

            # Get all active UUIDs
            all_uuids = await self.vector_store_service.get_all_uuids(include_deleted=False)
            total_chunks = len(all_uuids)
            logger.info(f"Total chunks to index: {total_chunks}")

            if total_chunks == 0:
                return SuccessResult(
                    data={
                        "indexed_count": 0,
                        "failed_count": 0,
                        "total_chunks": 0,
                        "indexing_time": 0.0
                    }
                )

            # Clear existing BM25 index if force is True
            if force:
                logger.info("Clearing existing BM25 index due to force=True")
                await self.vector_store_service.bm25_service.clear_index()

            # Process chunks in batches
            indexed_count = 0
            failed_count = 0

            for i in range(0, len(all_uuids), batch_size):
                batch_uuids = all_uuids[i:i + batch_size]
                logger.info(f"Processing batch: {i//batch_size + 1}, UUIDs: {len(batch_uuids)}")

                # Get chunks for this batch
                chunks = await self.vector_store_service.crud_service.get_chunks(
                    uuids=batch_uuids,
                    include_vectors=False
                )

                # Index each chunk for BM25
                for chunk_data in chunks:
                    try:
                        # Get text content for BM25 indexing
                        text_content = chunk_data.get("text", "") or chunk_data.get("body", "")
                        chunk_uuid = chunk_data.get("uuid", "")
                        
                        if text_content and chunk_uuid:
                            # Index chunk directly in BM25 service
                            await self.vector_store_service.bm25_service.index_document(chunk_uuid, text_content)
                            indexed_count += 1
                        else:
                            logger.warning(f"Skipping chunk {chunk_uuid}: no text content")

                    except Exception as e:
                        logger.error(f"Failed to index chunk {chunk_data.get('uuid', 'unknown')} for BM25: {e}")
                        failed_count += 1

            indexing_time = time.time() - start_time

            logger.info(f"BM25 reindexing completed: indexed={indexed_count}, failed={failed_count}, time={indexing_time:.2f}s")

            return SuccessResult(
                data={
                    "indexed_count": indexed_count,
                    "failed_count": failed_count,
                    "total_chunks": total_chunks,
                    "indexing_time": indexing_time
                }
            )

        except Exception as e:
            logger.error(f"BM25 reindexing failed: {e}")
            return ErrorResult(
                code="reindex_error",
                message=f"Failed to reindex chunks for BM25: {e}",
                details={"indexed_count": indexed_count if 'indexed_count' in locals() else 0, "failed_count": failed_count if 'failed_count' in locals() else 0}
            )


def make_reindex_bm25(vector_store_service) -> ReindexBM25Command:
    """
    Factory function to create ReindexBM25Command instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        Configured ReindexBM25Command instance
    """
    return ReindexBM25Command(vector_store_service)
