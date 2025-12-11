"""
Hard delete command implementation following mcp_proxy_adapter framework.

This command physically removes records from FAISS and Redis with service lock.
It integrates with chunk_metadata_adapter for validation and processing.
"""

import logging
from typing import Dict, Any, List

from vector_store.exceptions import InvalidParamsError, ValidationError, CommandError
from mcp_proxy_adapter.commands.result import ErrorResult

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import HardDeleteResult

logger = logging.getLogger(__name__)


class HardDeleteCommand(BaseVectorStoreCommand):
    """
    Hard delete command: physically removes records from FAISS and Redis with service lock.

    This command blocks all read/write operations during deletion by acquiring a service-wide lock.
    All active connections are blocked until the deletion is complete.

    Parameters:
        uuids (List[str], required): List of UUIDs to hard delete.

    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "deleted_count": 5,
                    "deleted_uuids": ["uuid1", "uuid2", ...]
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
        | service_locked      | Service is already locked      | When another operation holds the lock
        | invalid_uuids       | Invalid UUID format            | When UUIDs are malformed
        | vector_manager_missing | VectorIndexManager not available | When VectorIndexManager is not configured
        | lock_manager_missing   | ServiceLockManager not available | When ServiceLockManager is not configured
        | deletion_failed     | Physical deletion failed       | When FAISS or Redis deletion fails

    Examples:
        Success:
            { "success": true, "data": { "deleted_count": 2, "deleted_uuids": ["123e4567-e89b-12d3-a456-426614174000", "987fcdeb-51a2-43d1-b789-123456789abc"] } }
        Error:
            { "success": false, "error": { "code": "service_locked", "message": "Service is locked: hard_delete", "data": {} } }
    """

    name = "chunk_hard_delete"
    result_class = HardDeleteResult

    def __init__(self, vector_store_service):
        """
        Initialize command with required service.

        Args:
            vector_store_service: Service for vector store operations
        """
        super().__init__(vector_store_service)

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Returns:
            JSON schema for parameters
        """
        return {
            "type": "object",
            "properties": {
                "uuids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of UUIDs to hard delete. All records will be physically removed from FAISS and Redis.",
                    "minItems": 1
                }
            },
            "required": ["uuids"],
            "additionalProperties": False
        }

    @classmethod
    def get_result_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for successful result.

        Returns:
            JSON schema for result
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "const": True},
                "data": {
                    "type": "object",
                    "properties": {
                        "deleted_count": {"type": "integer", "description": "Number of successfully deleted records"},
                        "deleted_uuids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of deleted UUIDs"
                        }
                    },
                    "required": ["deleted_count", "deleted_uuids"]
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
        return super().get_error_schema(["service_locked", "invalid_uuids", "vector_manager_missing", "lock_manager_missing", "deletion_failed"])

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.

        Returns:
            Dictionary with command metadata
        """
        return {
            "name": cls.name,
            "description": cls.__doc__,
            "params": cls.get_schema(),
            "result_schema": cls.get_result_schema(),
            "error_schema": cls.get_error_schema(),
            "error_codes": [
                {"code": "service_locked", "description": "Service is already locked", "when": "When another operation holds the lock"},
                {"code": "invalid_uuids", "description": "Invalid UUID format", "when": "When UUIDs are malformed"},
                {"code": "vector_manager_missing", "description": "VectorIndexManager not available", "when": "When VectorIndexManager is not configured"},
                {"code": "lock_manager_missing", "description": "ServiceLockManager not available", "when": "When ServiceLockManager is not configured"},
                {"code": "deletion_failed", "description": "Physical deletion failed", "when": "When FAISS or Redis deletion fails"}
            ],
            "examples": {
                "success": {
                    "success": True,
                    "data": {
                        "deleted_count": 2,
                        "deleted_uuids": ["123e4567-e89b-12d3-a456-426614174000", "987fcdeb-51a2-43d1-b789-123456789abc"]
                    }
                },
                "error": {
                    "success": False,
                    "error": {
                        "code": "service_locked",
                        "message": "Service is locked: hard_delete",
                        "data": {}
                    }
                }
            }
        }

    async def execute(self, **params) -> HardDeleteResult:
        """
        Execute hard delete command.

        Args:
            **params: Command parameters including 'uuids' list

        Returns:
            HardDeleteResult with deletion status or ErrorResult on error
        """
        try:
            # Validate required parameters
            self.validate_required_params(params, ["uuids"])
            
            uuids = params["uuids"]
            
            # Validate UUIDs
            if not isinstance(uuids, list):
                return ErrorResult(
                    code="invalid_uuids",
                    message="Parameter 'uuids' must be an array",
                    details={"uuids": uuids}
                )
            
            if len(uuids) == 0:
                return ErrorResult(
                    code="invalid_uuids",
                    message="At least one UUID must be provided",
                    details={"uuids": uuids}
                )
            
            # Validate UUID format
            for uuid in uuids:
                if not isinstance(uuid, str) or len(uuid) == 0:
                    return ErrorResult(
                        code="invalid_uuids",
                        message=f"Invalid UUID format: {uuid}",
                        details={"uuid": uuid}
                    )
            
            # Perform hard delete through vector store service
            result = await self.vector_store_service.chunk_hard_delete(uuids, confirm=True)
            
            return HardDeleteResult(
                deleted_count=result.get("deleted_count", 0),
                deleted_uuids=result.get("deleted_uuids", [])
            )
            
        except InvalidParamsError as e:
            return ErrorResult(
                code="invalid_uuids",
                message=str(e),
                details=getattr(e, "data", None)
            )
        except ValidationError as e:
            return ErrorResult(
                code="invalid_uuids",
                message=str(e),
                details=getattr(e, "data", None)
            )
        except Exception as e:
            logger.error(f"Hard delete operation failed: {e}")
            return ErrorResult(
                code="deletion_failed",
                message="Unexpected error during hard delete",
                details={"uuids": uuids, "error": str(e)}
            )


def make_chunk_hard_delete(vector_store_service):
    """
    Factory function to create HardDeleteCommand instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        HardDeleteCommand instance
    """
    return HardDeleteCommand(vector_store_service)
