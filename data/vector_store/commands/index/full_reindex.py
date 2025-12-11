"""
Full reindex command for Vector Store.

This command performs a complete reindexing of all chunks in Redis to FAISS,
using the text field to generate new embeddings.
"""

import time
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult
from typing import Any, Dict, List
from vector_store.utils.schema_param_validator import validate_params_against_schema
from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import FullReindexResult

class FullReindexCommand(BaseVectorStoreCommand):
    """
    Perform a complete reindexing of all chunks in Redis to FAISS.
    For each chunk with text, generates a new embedding using the embedding service,
    adds it to FAISS, and updates the Redis mappings.
    
    This is useful when:
    - FAISS index was corrupted or lost
    - Embedding model was changed
    - Need to rebuild the entire vector index

    Parameters:
        (none)

    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "total_chunks": <int>,
                    "processed": <int>,
                    "failed": <int>,
                    "failed_uuids": [<str>, ...],
                    "duration_seconds": <float>
                }
            }
        Error:
            {
                "success": false,
                "error": {"code": "reindex_error", "message": "...", "data": {}}
            }

    Error codes:
        | Code          | Description                  | When
        |---------------|------------------------------|-----------------------------
        | reindex_error | Internal reindexing error    | Any exception during reindex |

    Examples:
        Success:
            {"success": true, "data": {"total_chunks": 100, "processed": 95, "failed": 5, "failed_uuids": ["uuid1", "uuid2"], "duration_seconds": 10.5}}
        Error:
            {"success": false, "error": {"code": "reindex_error", "message": "...", "data": {}}}
    """
    name = "full_reindex"
    result_class = FullReindexResult

    def __init__(self, vector_store_service):
        super().__init__(vector_store_service)

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }

    @classmethod
    def get_result_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "total_chunks": {"type": "integer", "description": "Total number of chunks found in Redis"},
                        "processed": {"type": "integer", "description": "Number of chunks successfully processed"},
                        "failed": {"type": "integer", "description": "Number of chunks that failed to process"},
                        "failed_uuids": {"type": "array", "items": {"type": "string"}, "description": "List of UUIDs that failed to process"},
                        "duration_seconds": {"type": "number", "description": "Total time taken for reindexing in seconds"}
                    },
                    "required": ["total_chunks", "processed", "failed", "failed_uuids", "duration_seconds"]
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
        return super().get_error_schema(["reindex_error"])

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.

        Returns:
            Dictionary with command metadata
        """
        error_codes = [
            {"code": "reindex_error", "description": "Internal reindexing error", "when": "Any exception during reindex"}
        ]
        
        return {
            "name": cls.name,
            "summary": "Perform complete reindexing of all chunks in Redis to FAISS",
            "description": cls.__doc__,
            "parameters": cls.get_schema(),
            "returns": cls.get_result_schema(),
            "error_codes": error_codes,
            "examples": [
                {
                    "description": "Successful reindexing",
                    "input": {},
                    "output": {
                        "success": True,
                        "data": {
                            "total_chunks": 100,
                            "processed": 95,
                            "failed": 5,
                            "failed_uuids": ["uuid1", "uuid2"],
                            "duration_seconds": 10.5
                        }
                    }
                },
                {
                    "description": "Error during reindexing",
                    "input": {},
                    "output": {
                        "success": False,
                        "error": {
                            "code": "reindex_error",
                            "message": "Failed to perform full reindex: No embedding service available",
                            "data": {}
                        }
                    }
                }
            ]
        }

    async def execute(self, **params) -> FullReindexResult:
        """
        Execute full reindex command.

        Args:
            **params: Command parameters (none required)

        Returns:
            FullReindexResult with reindexing statistics
        """
        self._start_execution()
        
        try:
            # Validate parameters
            validate_params_against_schema(params, self.get_schema())
            
            # Check if embedding service is available
            if not self.vector_store_service.embedding_service:
                raise Exception("No embedding service available for reindexing")
            
            # Get all UUIDs from Redis
            uuids = await self.vector_store_service.crud_service.get_all_record_ids()
            total_chunks = len(uuids)
            
            if total_chunks == 0:
                duration = time.time() - self._start_time
                self._log_command_execution(self.name, params, {
                    "total_chunks": 0,
                    "processed": 0,
                    "failed": 0,
                    "failed_uuids": []
                }, duration)
                return FullReindexResult(
                    total_chunks=0,
                    processed=0,
                    failed=0,
                    failed_uuids=[],
                    duration_seconds=duration
                )
            
            # Get chunks from Redis
            chunks = await self.vector_store_service.crud_service.get_chunks(uuids)
            texts = [(chunk['uuid'], chunk['text']) for chunk in chunks if chunk and chunk.get('text')]
            
            if not texts:
                duration = time.time() - self._start_time
                self._log_command_execution(self.name, params, {
                    "total_chunks": total_chunks,
                    "processed": 0,
                    "failed": 0,
                    "failed_uuids": []
                }, duration)
                return FullReindexResult(
                    total_chunks=total_chunks,
                    processed=0,
                    failed=0,
                    failed_uuids=[],
                    duration_seconds=duration
                )
            
            # Process chunks
            processed = 0
            failed = 0
            failed_uuids = []
            
            # Clear existing FAISS index
            await self.vector_store_service.faiss_service.clear_index()
            
            # Process in batches for better performance
            batch_size = 100
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                vectors = []
                uuids_to_index = []
                
                for uuid, text in batch:
                    try:
                        # Generate embedding
                        embedding = await self.vector_store_service.embedding_service.get_embedding(text)
                        if embedding is not None:
                            vectors.append(embedding)
                            uuids_to_index.append(uuid)
                        else:
                            failed += 1
                            failed_uuids.append(uuid)
                    except Exception as e:
                        failed += 1
                        failed_uuids.append(uuid)
                        continue
                
                if vectors:
                    try:
                        # Add vectors to FAISS
                        indices = await self.vector_store_service.faiss_service.add_vectors(vectors)
                        
                        # Update Redis mappings
                        idx_pipeline = await self.vector_store_service.crud_service.redis.pipeline()
                        for idx, uuid in zip(indices, uuids_to_index):
                            idx_pipeline.set(f"faiss_idx:{idx}", uuid)
                            idx_pipeline.hset(self.vector_store_service.crud_service.chunk_key(uuid), "faiss_idx", idx)
                        await idx_pipeline.execute()
                        
                        processed += len(indices)
                    except Exception as e:
                        failed += len(uuids_to_index)
                        failed_uuids.extend(uuids_to_index)
            
            duration = time.time() - self._start_time
            
            self._log_command_execution(self.name, params, {
                "total_chunks": total_chunks,
                "processed": processed,
                "failed": failed,
                "failed_uuids": failed_uuids
            }, duration)
            
            return FullReindexResult(
                total_chunks=total_chunks,
                processed=processed,
                failed=failed,
                failed_uuids=failed_uuids,
                duration_seconds=duration
            )
            
        except Exception as e:
            return self._handle_execution_error(e, self.name, params)


def make_full_reindex(vector_store_service) -> FullReindexCommand:
    """
    Factory function to create FullReindexCommand.

    Args:
        vector_store_service: VectorStoreService instance

    Returns:
        FullReindexCommand instance
    """
    return FullReindexCommand(vector_store_service) 