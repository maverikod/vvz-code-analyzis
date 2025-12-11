"""
Force delete by UUIDs command implementation following mcp_proxy_adapter framework.

This command force deletes records by a list of UUIDs without validation of UUID format.
It integrates with chunk_metadata_adapter for validation and processing.
"""

import logging
from typing import Dict, Any, List

from vector_store.exceptions import InvalidParamsError, ValidationError, CommandError
from mcp_proxy_adapter.commands.result import ErrorResult

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import ForceDeleteResult

logger = logging.getLogger(__name__)


class ForceDeleteByUuidsCommand(BaseVectorStoreCommand):
    """
    Force delete records by a list of UUIDs (no validation of UUID format).
    
    Performs two-stage deletion: mark as deleted, then physically remove.
    Tries to delete each record by key, regardless of whether the UUID is valid.

    Parameters:
        uuids (list of str, required): List of UUIDs (any strings) to delete.
        force (boolean, optional): Force flag to bypass restrictions (must be True for force delete).

    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "deleted": 5,
                    "not_found": 2,
                    "errors": 1,
                    "errors_uuids": ["bad-uuid"]
                }
            }
        Error:
            {
                "success": false,
                "error": {"code": "force_delete_error", "message": "...", "data": {}}
            }

    Error codes:
        | Code                | Description                  | When
        |---------------------|------------------------------|-----------------------------
        | force_delete_error  | Internal deletion error      | Any exception during delete |

    Examples:
        Success:
            {"success": true, "data": {"deleted": 5, "not_found": 2, "errors": 1, "errors_uuids": ["bad-uuid"]}}
        Error:
            {"success": false, "error": {"code": "force_delete_error", "message": "...", "data": {}}}
    """
    
    name = "force_delete_by_uuids"
    result_class = ForceDeleteResult

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
                    "minItems": 1,
                    "description": "List of UUIDs (any strings) to delete"
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force deletion without validation (must be True for force delete)"
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
                        "deleted": {"type": "integer", "description": "Number of successfully deleted records"},
                        "not_found": {"type": "integer", "description": "Number of records not found"},
                        "errors": {"type": "integer", "description": "Number of records with deletion errors"},
                        "errors_uuids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of UUIDs that failed to delete"
                        }
                    },
                    "required": ["deleted", "not_found", "errors", "errors_uuids"]
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
        return super().get_error_schema(["force_delete_error"])

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
                {"code": "force_delete_error", "description": "Internal deletion error", "when": "Any exception during delete"}
            ],
            "examples": {
                "success": {
                    "success": True,
                    "data": {
                        "deleted": 5,
                        "not_found": 2,
                        "errors": 1,
                        "errors_uuids": ["bad-uuid"]
                    }
                },
                "error": {
                    "success": False,
                    "error": {
                        "code": "force_delete_error",
                        "message": "Internal deletion error",
                        "data": {}
                    }
                },
                "with_force": {
                    "method": "force_delete_by_uuids",
                    "params": {
                        "uuids": ["uuid1", "uuid2"],
                        "force": True
                    },
                    "result": {
                        "success": True,
                        "data": {
                            "deleted": 2,
                            "not_found": 0,
                            "errors": 0,
                            "errors_uuids": []
                        }
                    }
                }
            }
        }

    async def execute(self, **params) -> ForceDeleteResult:
        """
        Execute force delete by UUIDs command.

        Args:
            **params: Command parameters including 'uuids' list

        Returns:
            ForceDeleteResult with deletion status or ErrorResult on error
        """
        try:
            # Validate required parameters
            self.validate_required_params(params, ["uuids"])
            
            uuids = params["uuids"]
            
            # Validate UUIDs
            if not isinstance(uuids, list):
                return ErrorResult(
                    code="force_delete_error",
                    message="Parameter 'uuids' must be an array",
                    details={"uuids": uuids}
                )
            
            if len(uuids) == 0:
                return ErrorResult(
                    code="force_delete_error",
                    message="Parameter 'uuids' cannot be empty",
                    details={"uuids": uuids}
                )
            
            # Perform force delete through vector store service
            force = params.get("force", False)
            result = await self.vector_store_service.force_delete_by_uuids(uuids, force=force)
            
            # Handle missing keys in result
            deleted = result.get("deleted", 0)
            not_found = result.get("not_found", 0)
            errors = result.get("errors", 0)
            errors_uuids = result.get("errors_uuids", [])
            
            return ForceDeleteResult(
                deleted=deleted,
                not_found=not_found,
                errors=errors,
                errors_uuids=errors_uuids
            )
            
        except InvalidParamsError as e:
            return ErrorResult(
                code="force_delete_error",
                message=str(e),
                details=getattr(e, "data", None)
            )
        except Exception as e:
            logger.error(f"Force delete operation failed: {e}")
            return ErrorResult(
                code="force_delete_error",
                message="Internal deletion error",
                details={"uuids": uuids, "error": str(e)}
            )


def make_force_delete_by_uuids(vector_store_service):
    """
    Factory function to create ForceDeleteByUuidsCommand instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        ForceDeleteByUuidsCommand instance
    """
    return ForceDeleteByUuidsCommand(vector_store_service)
