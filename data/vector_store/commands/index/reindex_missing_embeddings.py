import time
import numpy as np
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult
from typing import Any, Dict, List
from vector_store.utils.schema_param_validator import validate_params_against_schema
from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import ReindexMissingEmbeddingsResult

class ReindexMissingEmbeddingsCommand(BaseVectorStoreCommand):
    """
    Reindex all metadata records in Redis that are missing a valid embedding.
    For each such record, generates an embedding using the embedding service, adds it to FAISS, and updates Redis.
    Returns uuids for which errors occurred.

    Parameters:
        (none)

    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "updated": <int>,
                    "skipped": <int>,
                    "errors": <int>,
                    "errors_uuids": [<str>, ...]
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
            {"success": true, "data": {"updated": 10, "skipped": 5, "errors": 2, "errors_uuids": ["uuid1", "uuid2"]}}
        Error:
            {"success": false, "error": {"code": "reindex_error", "message": "...", "data": {}}}
    """
    name = "reindex_missing_embeddings"
    result_class = ReindexMissingEmbeddingsResult

    def __init__(self, vector_store_service):
        super().__init__(vector_store_service)
        self.vector_size = getattr(vector_store_service.faiss_service, 'vector_size', 384)

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
                        "updated": {"type": "integer", "description": "Number of records updated with new embedding"},
                        "skipped": {"type": "integer", "description": "Number of records skipped (already valid embedding or no text)"},
                        "errors": {"type": "integer", "description": "Number of records failed to update due to errors"},
                        "errors_uuids": {"type": "array", "items": {"type": "string"}, "description": "List of uuids for which errors occurred"}
                    },
                    "required": ["updated", "skipped", "errors", "errors_uuids"]
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
        
        examples = {
            "success": {
                "success": True,
                "data": {"updated": 10, "skipped": 5, "errors": 2, "errors_uuids": ["uuid1", "uuid2"]}
            },
            "error": {
                "success": False,
                "error": {
                    "code": "reindex_error",
                    "message": "Internal reindexing error",
                    "data": {}
                }
            }
        }
        
        return super().get_metadata(error_codes, examples)

    async def execute(self, **params) -> ReindexMissingEmbeddingsResult:
        self._start_execution()
        
        try:
            # Валидация параметров
            self.validate_required_params(params, [])
            
            updated = 0
            skipped = 0
            errors = 0
            errors_uuids: List[str] = []
            
            # Выполнение операции
            all_uuids = await self.vector_store_service.crud_service.get_all_record_ids()
            for uuid in all_uuids:
                try:
                    meta = await self.vector_store_service.crud_service.get_metadata(uuid)
                    embedding = meta.get("embedding")
                    if not (isinstance(embedding, list) and len(embedding) == self.vector_size and all(isinstance(x, (float, int)) for x in embedding)):
                        text = meta.get("body") or meta.get("text")
                        if not text:
                            skipped += 1
                            continue
                        try:
                            embedding = await self.vector_store_service.embedding_service.get_embedding(text)
                        except Exception:
                            errors += 1
                            errors_uuids.append(uuid)
                            continue
                        try:
                            np_vector = np.array(embedding, dtype=np.float32)
                            idx = await self.vector_store_service.faiss_service.add_vector(np_vector)
                        except Exception:
                            errors += 1
                            errors_uuids.append(uuid)
                            continue
                        try:
                            await self.vector_store_service.crud_service.save_metadata(uuid, meta, idx)
                            updated += 1
                        except Exception:
                            errors += 1
                            errors_uuids.append(uuid)
                    else:
                        skipped += 1
                except Exception:
                    errors += 1
                    errors_uuids.append(uuid)
            
            execution_time = time.time() - self._start_time
            self._log_command_execution(self.name, params, {
                "updated": updated, 
                "skipped": skipped, 
                "errors": errors, 
                "errors_uuids": errors_uuids
            }, execution_time)
            
            return ReindexMissingEmbeddingsResult(
                updated=updated,
                skipped=skipped,
                errors=errors,
                errors_uuids=errors_uuids
            )
            
        except Exception as e:
            execution_time = time.time() - self._start_time
            self._log_command_error(self.name, params, e, execution_time)
            return self._handle_execution_error(e, self.name, params)


def make_reindex_missing_embeddings(vector_store_service) -> ReindexMissingEmbeddingsCommand:
    """
    Factory function for creating ReindexMissingEmbeddingsCommand.
    
    Args:
        vector_store_service: Vector store service instance
        
    Returns:
        ReindexMissingEmbeddingsCommand instance
    """
    return ReindexMissingEmbeddingsCommand(vector_store_service)
