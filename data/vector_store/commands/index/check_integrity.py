"""
Data integrity check command for Vector Store.

This command checks integrity between Redis and FAISS data,
and performs reindexing if discrepancies are found.
"""

import time
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult
from typing import Any, Dict, List
from vector_store.utils.schema_param_validator import validate_params_against_schema
from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import IntegrityCheckResult

class CheckIntegrityCommand(BaseVectorStoreCommand):
    """
    Check data integrity between Redis and FAISS.
    
    Compares the number of vectors in Redis and FAISS, and performs
    reindexing if discrepancies are found. This is critical for
    ensuring data consistency after server restarts.
    
    Parameters:
        auto_fix: Whether to automatically reindex if discrepancies found (default: true)
        force_reindex: Force reindexing even if counts match (default: false)
        
    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "redis_count": <int>,
                    "faiss_count": <int>,
                    "discrepancy_found": <bool>,
                    "reindexed": <bool>,
                    "duration_seconds": <float>,
                    "details": <str>
                }
            }
        Error:
            {
                "success": false,
                "error": {"code": "integrity_error", "message": "...", "data": {}}
            }

    Error codes:
        | Code            | Description                  | When
        |-----------------|------------------------------|-----------------------------
        | integrity_error | Internal integrity error     | Any exception during check |

    Examples:
        Success:
            {"success": true, "data": {"redis_count": 1000, "faiss_count": 950, "discrepancy_found": true, "reindexed": true, "duration_seconds": 15.5, "details": "Reindexed 50 missing vectors"}}
        Error:
            {"success": false, "error": {"code": "integrity_error", "message": "...", "data": {}}}
    """
    name = "check_integrity"
    result_class = IntegrityCheckResult

    def __init__(self, vector_store_service):
        super().__init__(vector_store_service)

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "auto_fix": {
                    "type": "boolean",
                    "description": "Automatically reindex if discrepancies found",
                    "default": True
                },
                "force_reindex": {
                    "type": "boolean",
                    "description": "Force reindexing even if counts match",
                    "default": False
                }
            },
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
                        "redis_count": {"type": "integer", "description": "Number of records in Redis"},
                        "faiss_count": {"type": "integer", "description": "Number of vectors in FAISS"},
                        "discrepancy_found": {"type": "boolean", "description": "Whether discrepancy was found"},
                        "reindexed": {"type": "boolean", "description": "Whether reindexing was performed"},
                        "duration_seconds": {"type": "number", "description": "Time taken for check in seconds"},
                        "details": {"type": "string", "description": "Detailed information about the operation"}
                    },
                    "required": ["redis_count", "faiss_count", "discrepancy_found", "reindexed", "duration_seconds", "details"]
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
        return super().get_error_schema(["integrity_error"])

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.

        Returns:
            Dictionary with command metadata
        """
        error_codes = [
            {"code": "integrity_error", "description": "Internal integrity error", "when": "Any exception during check"}
        ]
        
        return {
            "name": cls.name,
            "summary": "Check data integrity between Redis and FAISS",
            "description": cls.__doc__,
            "parameters": cls.get_schema(),
            "returns": cls.get_result_schema(),
            "error_codes": error_codes,
            "examples": [
                {
                    "description": "Successful integrity check with reindexing",
                    "input": {"auto_fix": True},
                    "output": {
                        "success": True,
                        "data": {
                            "redis_count": 1000,
                            "faiss_count": 950,
                            "discrepancy_found": True,
                            "reindexed": True,
                            "duration_seconds": 15.5,
                            "details": "Reindexed 50 missing vectors"
                        }
                    }
                },
                {
                    "description": "Integrity check passed",
                    "input": {"auto_fix": False},
                    "output": {
                        "success": True,
                        "data": {
                            "redis_count": 1000,
                            "faiss_count": 1000,
                            "discrepancy_found": False,
                            "reindexed": False,
                            "duration_seconds": 0.5,
                            "details": "Data integrity verified"
                        }
                    }
                }
            ]
        }

    async def execute(self, **params) -> IntegrityCheckResult:
        """
        Execute integrity check command.

        Args:
            **params: Command parameters
                auto_fix: Whether to automatically reindex if discrepancies found
                force_reindex: Force reindexing even if counts match

        Returns:
            IntegrityCheckResult with integrity information
        """
        self._start_execution()
        
        try:
            # Validate parameters
            validate_params_against_schema(params, self.get_schema())
            
            auto_fix = params.get("auto_fix", True)
            force_reindex = params.get("force_reindex", False)
            
            # Get counts
            redis_count = await self.vector_store_service.count_records()
            faiss_count = await self.vector_store_service.faiss_service.count()
            
            # Check for discrepancy
            discrepancy_found = redis_count != faiss_count
            reindexed = False
            details = ""
            
            if discrepancy_found:
                details = f"Discrepancy found: Redis has {redis_count} records, FAISS has {faiss_count} vectors"
                
                if auto_fix:
                    details += f". Reindexing {redis_count} records..."
                    await self.vector_store_service.full_reindex(self.vector_store_service.embedding_service)
                    reindexed = True
                    details += " Completed."
                else:
                    details += ". Auto-fix disabled."
            elif force_reindex:
                details = f"Force reindexing {redis_count} records..."
                await self.vector_store_service.full_reindex(self.vector_store_service.embedding_service)
                reindexed = True
                details += " Completed."
            else:
                details = "Data integrity verified"
            
            duration = time.time() - self._start_time
            
            self._log_command_execution(self.name, params, {
                "redis_count": redis_count,
                "faiss_count": faiss_count,
                "discrepancy_found": discrepancy_found,
                "reindexed": reindexed,
                "duration_seconds": duration,
                "details": details
            }, duration)
            
            return IntegrityCheckResult(
                redis_count=redis_count,
                faiss_count=faiss_count,
                discrepancy_found=discrepancy_found,
                reindexed=reindexed,
                duration_seconds=duration,
                details=details
            )
            
        except Exception as e:
            return self._handle_execution_error(e, self.name, params)


def make_check_integrity(vector_store_service) -> CheckIntegrityCommand:
    """
    Factory function to create CheckIntegrityCommand.

    Args:
        vector_store_service: VectorStoreService instance

    Returns:
        CheckIntegrityCommand instance
    """
    return CheckIntegrityCommand(vector_store_service) 