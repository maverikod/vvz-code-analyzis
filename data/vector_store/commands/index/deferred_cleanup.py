"""
Deferred cleanup command implementation.

This module provides functionality for physically removing soft-deleted records
from FAISS and Redis storage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult
from vector_store.services.vector_store_service import VectorStoreService
from typing import Any, Dict
from vector_store.utils.schema_param_validator import validate_params_against_schema

class DeferredCleanupResult(SuccessResult):
    """Result class for deferred cleanup command."""
    pass

class DeferredCleanupCommand(Command):
    """
    Deferred cleanup command: physically removes soft-deleted records from FAISS and Redis.

    This command performs cleanup of records that were previously soft-deleted (marked as deleted).
    It removes them from FAISS index and Redis storage to free up space.

    Parameters:
        None (no parameters required)

    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "cleaned_count": 10,
                    "message": "Successfully cleaned up 10 soft-deleted records"
                }
            }
        Error:
            {
                "success": false,
                "error": { "code": "<error_code>", "message": "<описание>", "data": { ... } }
            }

    Error codes:
        | Code                | Description                    | When
        |---------------------|--------------------------------|-------------------
        | vector_manager_missing | VectorIndexManager not available | When VectorIndexManager is not configured
        | cleanup_failed      | Cleanup operation failed       | When FAISS or Redis cleanup fails
        | no_deleted_records  | No soft-deleted records found  | When no records are marked for deletion

    Examples:
        Success:
            { "success": true, "data": { "cleaned_count": 5, "message": "Successfully cleaned up 5 soft-deleted records" } }
        Error:
            { "success": false, "error": { "code": "no_deleted_records", "message": "No soft-deleted records found", "data": {} } }
    """

    name = "chunk_deferred_cleanup"
    result_class = DeferredCleanupResult

    def __init__(self, vector_store_service: VectorStoreService):
        self.vector_store_service = vector_store_service

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
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
                        "cleaned_count": {"type": "integer", "description": "Number of cleaned up records"},
                        "message": {"type": "string", "description": "Human-readable result message"}
                    },
                    "required": ["cleaned_count", "message"]
                }
            },
            "required": ["success", "data"]
        }
    @classmethod
    def get_error_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "error": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "enum": ["vector_manager_missing", "cleanup_failed", "no_deleted_records"]
                        },
                        "message": {"type": "string"},
                        "data": {"type": "object"}
                    },
                    "required": ["code", "message"]
                }
            },
            "required": ["success", "error"]
        }

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "description": cls.__doc__,
            "params": cls.get_schema(),
            "result_schema": cls.get_result_schema(),
            "error_schema": cls.get_error_schema(),
            "error_codes": [
                {"code": "vector_manager_missing", "description": "VectorIndexManager not available", "when": "When VectorIndexManager is not configured"},
                {"code": "cleanup_failed", "description": "Cleanup operation failed", "when": "When FAISS or Redis cleanup fails"},
                {"code": "no_deleted_records", "description": "No soft-deleted records found", "when": "When no records are marked for deletion"}
            ],
            "examples": [
                {
                    "name": "Cleanup with deleted records",
                    "command": "chunk_deferred_cleanup",
                    "params": {},
                    "result": {"cleaned_count": 3, "message": "Successfully cleaned up 3 soft-deleted records"}
                },
                {
                    "name": "Cleanup with no deleted records",
                    "command": "chunk_deferred_cleanup",
                    "params": {},
                    "result": {"cleaned_count": 0, "message": "No soft-deleted records found"}
                }
            ],
            "notes": [
                "This command removes records that were previously soft-deleted using chunk_delete.",
                "Records are physically removed from both FAISS and Redis storage.",
                "This operation frees up storage space and improves performance.",
                "Use this command periodically or when you need to reclaim storage space.",
                "This operation cannot be undone - ensure you want to permanently remove the records."
            ]
        }

    async def execute(self, **params) -> SuccessResult:
        validate_params_against_schema(params, self.get_schema())

        try:
            # Call the chunk_deferred_cleanup method from VectorStoreService
            # Note: dry_run and batch_size are not supported in the current implementation
            result = await self.vector_store_service.chunk_deferred_cleanup()
            
            return DeferredCleanupResult(
                data={
                    "cleaned_count": result.get("cleaned_count", 0),
                    "message": result.get("message", "Cleanup completed")
                }
            )

        except ValueError as e:
            return ErrorResult(
                message=str(e),
                code=-32002,
                details={"error_code": "cleanup_failed"}
            )
        except Exception as e:
            return ErrorResult(
                message=f"Unexpected error during deferred cleanup: {str(e)}",
                code=-32002,
                details={"error_code": "cleanup_failed"}
            )

def make_chunk_deferred_cleanup(vector_store_service):
    """
    Factory function to create DeferredCleanupCommand instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        DeferredCleanupCommand instance
    """
    return DeferredCleanupCommand(vector_store_service)
