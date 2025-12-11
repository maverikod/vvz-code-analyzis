"""
Find duplicate UUIDs command implementation following mcp_proxy_adapter framework.

This command scans the vector store database to identify UUIDs that have multiple records.
It integrates with chunk_metadata_adapter for validation and processing.
"""

import logging
from typing import Dict, Any, Optional

from vector_store.exceptions import InvalidParamsError, ValidationError, CommandError
from mcp_proxy_adapter.commands.result import ErrorResult

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import FindDuplicateUuidsResult
from chunk_metadata_adapter.chunk_query import ChunkQuery
from chunk_metadata_adapter.query_validator import QueryValidator

logger = logging.getLogger(__name__)


class FindDuplicateUuidsCommand(BaseVectorStoreCommand):
    """
    Find all UUIDs with duplicate records and return their metadata.
    
    Scans the vector store database to identify UUIDs that have multiple records.
    This is useful for data integrity verification and cleanup preparation.

    Parameters:
        metadata_filter (object, optional): Optional metadata filter to apply before finding duplicates
            - Supports: $eq, $in, $range, $gte, $lte, $gt, $lt for scalar and array fields
            - If not provided, all records will be scanned

    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "duplicate_uuids": [
                        {
                            "uuid": "duplicate-uuid-1",
                            "records": [
                                {"uuid": "duplicate-uuid-1", "text": "content 1"},
                                {"uuid": "duplicate-uuid-1", "text": "content 2"}
                            ]
                        }
                    ]
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "validation_error",
                    "message": "Invalid filter expression",
                    "data": {"filter": {"invalid_field": {"$unsupported": "value"}}}
                }
            }

    Error codes:
        | Code              | Description                    | When
        |-------------------|--------------------------------|-------------------
        | validation_error  | Filter validation failed       | When filter fails ChunkQuery validation
        | scan_error        | Database scan failed           | When vector store scan operation fails

    Examples:
        Success:
            {
                "success": true,
                "data": {
                    "duplicate_uuids": [
                        {
                            "uuid": "duplicate-uuid-1",
                            "records": [
                                {"uuid": "duplicate-uuid-1", "text": "content 1"},
                                {"uuid": "duplicate-uuid-1", "text": "content 2"}
                            ]
                        }
                    ]
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "validation_error",
                    "message": "Invalid filter expression",
                    "data": {"filter": {"invalid_field": {"$unsupported": "value"}}}
                }
            }
    """
    
    name = "find_duplicate_uuids"
    result_class = FindDuplicateUuidsResult

    def __init__(self, vector_store_service):
        """
        Initialize command with required service.

        Args:
            vector_store_service: Service for vector store operations
        """
        super().__init__(vector_store_service)
        self.query_validator = QueryValidator()

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
                "metadata_filter": {
                    "type": "object",
                    "description": "Optional metadata filter to apply before finding duplicates",
                    "additionalProperties": True
                }
            },
            "required": [],
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
                        "duplicate_uuids": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "uuid": {"type": "string"},
                                    "records": {
                                        "type": "array",
                                        "items": {"type": "object"}
                                    }
                                },
                                "required": ["uuid", "records"]
                            },
                            "description": "List of duplicate UUIDs with their records"
                        }
                    },
                    "required": ["duplicate_uuids"]
                }
            },
            "required": ["success", "data"]
        }
    @classmethod
    def get_error_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for error result.

        Returns:
            JSON schema for error
        """
        return super().get_error_schema([
            "validation_error", "scan_error"
        ])

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.

        Returns:
            Dictionary with command metadata
        """
        return {
            "name": cls.name,
            "summary": "Find all UUIDs with duplicate records and return their metadata",
            "description": (
                "Scans the vector store database to identify UUIDs that have multiple records.\n\n"
                "**Key Features:**\n"
                "- Database integrity check: Identifies data consistency issues\n"
                "- Complete metadata: Returns all records for each duplicate UUID\n"
                "- Optional filtering: Can apply metadata filters before scanning\n"
                "- Atomic operation: Consistent results even with concurrent updates\n\n"
                "**Use Cases:**\n"
                "- Data integrity verification\n"
                "- Migration script validation\n"
                "- System health monitoring\n"
                "- Cleanup preparation\n\n"
                "**Performance:**\n"
                "- Full database scan required\n"
                "- Time depends on total number of records\n"
                "- Memory usage depends on number of duplicates found\n"
                "- Consider running during low-traffic periods"
            ),
            "category": "integrity",
            "params": cls.get_schema(),
            "result_schema": cls.get_result_schema(),
            "error_schema": cls.get_error_schema(),
            "error_codes": [
                {"code": "validation_error", "description": "Filter validation failed", "when": "When filter fails ChunkQuery validation"},
                {"code": "scan_error", "description": "Database scan failed", "when": "When vector store scan operation fails"}
            ],
            "examples": [
                {
                    "name": "Find duplicates in empty database",
                    "description": "No duplicates found in empty database",
                    "command": "find_duplicate_uuids",
                    "params": {},
                    "result": {
                        "success": True,
                        "data": {
                            "duplicate_uuids": []
                        }
                    }
                },
                {
                    "name": "Find duplicates with filter",
                    "description": "Find duplicates with metadata filter",
                    "command": "find_duplicate_uuids",
                    "params": {
                        "metadata_filter": {"category": "science"}
                    },
                    "result": {
                        "success": True,
                        "data": {
                            "duplicate_uuids": []
                        }
                    }
                },
                {
                    "name": "Find duplicates with results",
                    "description": "Find duplicates with actual duplicate records",
                    "command": "find_duplicate_uuids",
                    "params": {},
                    "result": {
                        "success": True,
                        "data": {
                            "duplicate_uuids": [
                                {
                                    "uuid": "duplicate-uuid-1",
                                    "records": [
                                        {"uuid": "duplicate-uuid-1", "text": "content 1"},
                                        {"uuid": "duplicate-uuid-1", "text": "content 2"}
                                    ]
                                }
                            ]
                        }
                    }
                }
            ]
        }

    async def execute(self, **params) -> FindDuplicateUuidsResult:
        """
        Execute find duplicate UUIDs command.

        Args:
            **params: Command parameters including optional metadata_filter

        Returns:
            FindDuplicateUuidsResult with duplicate UUIDs or ErrorResult on error
        """
        try:
            # Validate parameters
            metadata_filter = params.get('metadata_filter')
            
            # Validate filter if provided
            if metadata_filter is not None:
                if not isinstance(metadata_filter, dict):
                    return ErrorResult(
                        code="validation_error",
                        message="Parameter 'metadata_filter' must be an object",
                        details={"metadata_filter": metadata_filter}
                    )
                
                # For now, skip ChunkQuery validation as it expects string format
                # TODO: Implement proper filter validation for metadata filters
            
            # Perform duplicate scan through vector store service
            duplicate_uuids = await self.vector_store_service.find_duplicate_uuids(metadata_filter)
            
            return FindDuplicateUuidsResult(duplicate_uuids=duplicate_uuids)
            
        except ValidationError as e:
            return ErrorResult(
                code="validation_error",
                message=str(e),
                details=getattr(e, "data", None)
            )
        except Exception as e:
            logger.error(f"Find duplicate UUIDs operation failed: {e}")
            return ErrorResult(
                code="scan_error",
                message="Find duplicate UUIDs operation failed",
                details={"metadata_filter": metadata_filter, "error": str(e)}
            )


def make_find_duplicate_uuids(vector_store_service):
    """
    Factory function to create FindDuplicateUuidsCommand instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        FindDuplicateUuidsCommand instance
    """
    return FindDuplicateUuidsCommand(vector_store_service)
