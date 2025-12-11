"""
Clean FAISS orphans command for removing vectors without UUID mappings.

This command removes vectors from FAISS index that don't have corresponding
UUID mappings in Redis, effectively cleaning up orphaned vectors.
"""

import logging
from typing import Dict, Any, Optional, Union

from vector_store.exceptions import CommandError
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from vector_store.commands.base import BaseVectorStoreCommand

logger = logging.getLogger(__name__)


class CleanFaissOrphansCommand(BaseVectorStoreCommand):
    """
    Clean FAISS orphans command for removing vectors without UUID mappings.

    This command removes vectors from FAISS index that don't have corresponding
    UUID mappings in Redis, effectively cleaning up orphaned vectors.
    """
    
    name = "clean_faiss_orphans"

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
                "dry_run": {
                    "type": "boolean",
                    "description": "If True, only report what would be cleaned without actually cleaning",
                    "default": False
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
                        "cleaned_count": {"type": "integer", "minimum": 0},
                        "total_vectors": {"type": "integer", "minimum": 0},
                        "valid_vectors": {"type": "integer", "minimum": 0},
                        "orphaned_vectors": {"type": "integer", "minimum": 0},
                        "cleaned_redis_keys": {"type": "integer", "minimum": 0},
                        "orphaned_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "List of orphaned indices (only in dry run)"
                        },
                        "dry_run": {"type": "boolean"}
                    },
                    "required": ["cleaned_count", "total_vectors", "valid_vectors", "orphaned_vectors", "dry_run"]
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
            "invalid_params", "validation_error", "command_error", "unexpected_error"
        ])

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.

        Returns:
            Dictionary with command metadata
        """
        error_codes = [
            {"code": "invalid_params", "description": "Invalid parameters provided", "when": "When parameters are invalid"},
            {"code": "validation_error", "description": "Validation failed", "when": "When data validation fails"},
            {"code": "command_error", "description": "Command execution failed", "when": "When command operation fails"},
            {"code": "unexpected_error", "description": "Unexpected error occurred", "when": "When an unexpected error occurs"}
        ]
        
        examples = {
            "success": {
                "success": True,
                "data": {
                    "cleaned_count": 5,
                    "total_vectors": 100,
                    "valid_vectors": 95,
                    "orphaned_vectors": 0,
                    "cleaned_redis_keys": 3,
                    "dry_run": False
                }
            },
            "error": {
                "success": False,
                "error": {
                    "code": "unexpected_error",
                    "message": "Failed to clean FAISS orphans: Redis connection error",
                    "data": {"details": {"error": "Redis connection error"}}
                }
            }
        }
        
        return super().get_metadata(error_codes, examples)

    async def execute(
        self,
        dry_run: Optional[bool] = None,
        **params
    ) -> Union[SuccessResult, ErrorResult]:
        """
        Execute clean FAISS orphans command.

        Args:
            dry_run: If True, only report what would be cleaned without actually cleaning
            **params: Additional parameters

        Returns:
            SuccessResult with cleaning statistics or ErrorResult on error
        """
        try:
            # Set defaults
            if dry_run is None:
                dry_run = False

            logger.info(f"Starting FAISS orphans cleaning (dry_run={dry_run})")

            # Get all UUIDs from Redis using CRUD service
            all_uuids = await self.vector_store_service.crud_service.get_all_record_ids()
            logger.info(f"Found {len(all_uuids)} UUIDs in Redis")

            # Get FAISS indices for these UUIDs
            valid_indices = []
            for uuid in all_uuids:
                chunk_data = await self.vector_store_service.crud_service.get_chunk(uuid)
                if chunk_data and 'faiss_idx' in chunk_data:
                    try:
                        faiss_idx = int(chunk_data['faiss_idx'])
                        valid_indices.append(faiss_idx)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid FAISS index for UUID {uuid}: {chunk_data.get('faiss_idx')}")

            logger.info(f"Found {len(valid_indices)} valid FAISS indices")

            # Get current FAISS index size
            current_size = self.vector_store_service.faiss_service.index.ntotal
            logger.info(f"Current FAISS index size: {current_size}")

            # Calculate orphaned indices
            orphaned_indices = []
            for i in range(current_size):
                if i not in valid_indices:
                    orphaned_indices.append(i)

            logger.info(f"Found {len(orphaned_indices)} orphaned indices")

            if not orphaned_indices:
                return SuccessResult(
                    data={
                        "cleaned_count": 0,
                        "total_vectors": current_size,
                        "valid_vectors": len(valid_indices),
                        "orphaned_vectors": 0,
                        "dry_run": dry_run
                    },
                    message="No orphaned vectors found"
                )

            if dry_run:
                return SuccessResult(
                    data={
                        "cleaned_count": 0,
                        "total_vectors": current_size,
                        "valid_vectors": len(valid_indices),
                        "orphaned_vectors": len(orphaned_indices),
                        "orphaned_indices": orphaned_indices[:10],  # Show first 10
                        "dry_run": dry_run
                    },
                    message=f"Would clean {len(orphaned_indices)} orphaned vectors (dry run)"
                )

            # Actually clean the orphans
            logger.info(f"Cleaning {len(orphaned_indices)} orphaned vectors")
            
            # Remove orphaned vectors from FAISS
            await self.vector_store_service.faiss_service.delete_vectors(orphaned_indices)
            
            # Clean up orphaned Redis keys using CRUD service
            cleaned_keys = 0
            for idx in orphaned_indices:
                key = f"faiss_idx:{idx}"
                if await self.vector_store_service.crud_service.redis.exists(key):
                    await self.vector_store_service.crud_service.redis.delete(key)
                    cleaned_keys += 1

            logger.info(f"Cleaned {cleaned_keys} orphaned Redis keys")

            # Get new FAISS index size
            new_size = self.vector_store_service.faiss_service.index.ntotal
            logger.info(f"New FAISS index size: {new_size}")

            return SuccessResult(
                data={
                    "cleaned_count": len(orphaned_indices),
                    "total_vectors": new_size,
                    "valid_vectors": len(valid_indices),
                    "orphaned_vectors": 0,
                    "cleaned_redis_keys": cleaned_keys,
                    "dry_run": dry_run
                },
                message=f"Successfully cleaned {len(orphaned_indices)} orphaned vectors"
            )

        except Exception as e:
            logger.error(f"Error during FAISS orphans cleaning: {e}", exc_info=True)
            return ErrorResult(message=f"Failed to clean FAISS orphans: {e}")


def make_clean_faiss_orphans(vector_store_service):
    return CleanFaissOrphansCommand(vector_store_service)
