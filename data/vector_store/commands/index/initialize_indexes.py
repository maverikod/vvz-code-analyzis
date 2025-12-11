"""
Initialize indexes command implementation.

This command initializes metadata indexes for fast search operations.
"""

import logging
from typing import Dict, Any, Optional

from vector_store.exceptions import (
    InvalidParamsError, ValidationError, CommandError, CreationError,
    UnexpectedError
)

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.base_result import BaseCommandResult
from mcp_proxy_adapter.commands.result import ErrorResult
from vector_store.services.index_manager.base import IndexType

logger = logging.getLogger(__name__)


class InitializeIndexesCommand(BaseVectorStoreCommand):
    """
    Initialize metadata indexes for fast search operations.

    This command creates indexes for metadata fields to enable fast O(1) search
    instead of O(n) scanning. It supports all field types including scalar,
    array, and range fields.

    Parameters:
        fields (object, optional): Dictionary of field names and their index types
            - If not provided, uses default fields (uuid, source_id, category, etc.)
            - Supported types: "scalar", "array", "range"

    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "initialized_fields": {
                        "uuid": true,
                        "source_id": true,
                        "category": true
                    },
                    "total_fields": 3,
                    "successful_fields": 3,
                    "failed_fields": 0
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "initialization_error",
                    "message": "Failed to initialize indexes",
                    "data": {"failed_fields": ["invalid_field"]}
                }
            }

    Error codes:
        | Code                  | Description                    | When
        |-----------------------|--------------------------------|-------------------
        | invalid_params        | Invalid parameters provided    | When fields parameter is invalid
        | initialization_error  | Index initialization failed    | When index creation fails
        | service_unavailable   | Index service not available    | When IndexManager is not available

    Examples:
        Success:
            {
                "success": true,
                "data": {
                    "initialized_fields": {
                        "uuid": true,
                        "source_id": true,
                        "category": true
                    },
                    "total_fields": 3,
                    "successful_fields": 3,
                    "failed_fields": 0
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "initialization_error",
                    "message": "Failed to initialize indexes",
                    "data": {"failed_fields": ["invalid_field"]}
                }
            }
    """

    name = "initialize_indexes"
    result_class = BaseCommandResult

    async def execute(self, **params) -> BaseCommandResult:
        """
        Execute initialize indexes command.

        Args:
            **params: Command parameters including fields

        Returns:
            BaseCommandResult with initialization results or ErrorResult on error
        """
        try:
            # Extract fields parameter
            fields = params.get("fields")
            
            # Validate fields if provided
            if fields is not None:
                if not isinstance(fields, dict):
                    return ErrorResult(
                        code="invalid_params",
                        message="Fields parameter must be a dictionary",
                        details={"fields_type": type(fields).__name__}
                    )
                
                # Validate field types
                for field_name, field_type in fields.items():
                    if not isinstance(field_name, str):
                        return ErrorResult(
                            code="invalid_params",
                            message="Field names must be strings",
                            details={"invalid_field_name": field_name}
                        )
                    
                    if not isinstance(field_type, str):
                        return ErrorResult(
                            code="invalid_params",
                            message="Field types must be strings",
                            details={"invalid_field_type": field_type}
                        )
                    
                    if field_type not in ["scalar", "array", "range"]:
                        return ErrorResult(
                            code="invalid_params",
                            message="Invalid field type",
                            details={"field_name": field_name, "field_type": field_type}
                        )

            # Check if IndexManager is available
            if not hasattr(self.vector_store_service.crud_service, 'index_manager') or \
               not self.vector_store_service.crud_service.index_manager:
                return ErrorResult(
                    code="service_unavailable",
                    message="IndexManager is not available",
                    details={"service": "IndexManager"}
                )

            # Convert string types to IndexType enums if fields provided
            index_fields = None
            if fields:
                index_fields = {}
                for field_name, field_type in fields.items():
                    if field_type == "scalar":
                        index_fields[field_name] = IndexType.SCALAR
                    elif field_type == "array":
                        index_fields[field_name] = IndexType.ARRAY
                    elif field_type == "range":
                        index_fields[field_name] = IndexType.RANGE

            # Initialize indexes
            results = await self.vector_store_service.crud_service.index_manager.initialize_indexes(index_fields)
            
            # Calculate statistics
            total_fields = len(results)
            successful_fields = sum(1 for success in results.values() if success)
            failed_fields = total_fields - successful_fields
            
            # Prepare response data
            response_data = {
                "initialized_fields": results,
                "total_fields": total_fields,
                "successful_fields": successful_fields,
                "failed_fields": failed_fields
            }
            
            # Check if any fields failed
            if failed_fields > 0:
                failed_field_names = [field for field, success in results.items() if not success]
                return ErrorResult(
                    code="initialization_error",
                    message=f"Failed to initialize {failed_fields} out of {total_fields} fields",
                    details={"failed_fields": failed_field_names, "results": response_data}
                )
            
            logger.info(f"Successfully initialized {successful_fields} indexes")
            return BaseCommandResult(data=response_data)

        except InvalidParamsError as e:
            return ErrorResult(
                code="invalid_params",
                message=str(e),
                details=getattr(e, "data", None)
            )
        except ValidationError as e:
            return ErrorResult(
                code="validation_error",
                message=str(e),
                details=getattr(e, "data", None)
            )
        except Exception as e:
            logger.error(f"Unexpected error during index initialization: {e}")
            return ErrorResult(
                code="unexpected_error",
                message=f"Unexpected error during index initialization: {e}",
                details={"operation": "initialize_indexes"}
            )


def make_initialize_indexes(vector_store_service) -> InitializeIndexesCommand:
    """
    Factory function to create InitializeIndexesCommand instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        Configured InitializeIndexesCommand instance
    """
    return InitializeIndexesCommand(vector_store_service)
