"""
Chunk creation command implementation following mcp_proxy_adapter framework.

This command creates one or many chunk records in the vector store with 384-dimensional embeddings.
It integrates with chunk_metadata_adapter for validation and processing.
"""

import logging
import uuid
from typing import Dict, Any, List, Optional

from vector_store.exceptions import (
    InvalidParamsError, ValidationError, CommandError, CreationError,
    EmbeddingGenerationError, EmbeddingValidationError, ChunkValidationError,
    VectorStoreServiceError, UnexpectedError
)

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import CreateResult
from mcp_proxy_adapter.commands.result import ErrorResult
from chunk_metadata_adapter.semantic_chunk import SemanticChunk
from chunk_metadata_adapter.metadata_builder import ChunkMetadataBuilder
from chunk_metadata_adapter.utils import ChunkId
from chunk_metadata_adapter.data_types import ChunkType, ChunkRole, ChunkStatus, BlockType, LanguageEnum

logger = logging.getLogger(__name__)


class UpsertCommand(BaseVectorStoreCommand):
    """
    Creates one or many chunk records in the vector store with 384-dimensional embeddings.

    This command accepts an array of chunk metadata objects, validates each chunk through
    SemanticChunk validation, and stores them in the vector store. Each chunk is processed
    atomically - if any chunk fails validation, the entire operation fails.

    Parameters:
        chunks (array, required): Array of chunk metadata objects for creation
            - Each chunk must have body and text fields (required)
      - All other fields are optional or auto-generated
            - See SemanticChunk for complete field definitions

    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "created_count": 2,
                    "chunks": [
                        {"uuid": "123e4567-e89b-12d3-a456-426614174000", "status": "created"},
                        {"uuid": "456e7890-f12c-34d5-e678-901234567890", "status": "created"}
                    ]
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "validation_error",
                    "message": "Invalid chunk data at index 0: body field is required",
                    "data": {"chunk_index": 0, "field": "body"}
                }
            }

    Error codes:
        | Code              | Description                    | When
        |-------------------|--------------------------------|-------------------
        | invalid_params    | Invalid parameters provided    | When chunks array is missing or invalid
        | validation_error  | Chunk validation failed        | When chunk data fails SemanticChunk validation
        | creation_error    | Failed to create chunk         | When vector store operation fails
        | embedding_error   | Failed to generate embedding   | When embedding service fails

    Examples:
        Success:
            {
                "success": true,
                "data": {
                    "created_count": 1,
                    "chunks": [{"uuid": "123e4567-e89b-12d3-a456-426614174000", "status": "created"}]
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "validation_error",
                    "message": "Invalid chunk data: body field is required",
                    "data": {"chunk_index": 0, "field": "body"}
                }
            }
    """

    name = "upsert"
    result_class = CreateResult

    def __init__(self, vector_store_service):
        """
        Initialize command with required service.

        Args:
            vector_store_service: Service for vector store operations
        """
        super().__init__(vector_store_service)
        self.metadata_builder = ChunkMetadataBuilder()

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
                "chunks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "description": "SemanticChunk object with all required and optional fields",
                        "additionalProperties": True
                    },
                    "description": "Array of SemanticChunk objects for upsert",
                    "minItems": 1
                }
            },
            "required": ["chunks"],
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
                        "created_count": {"type": "integer", "minimum": 0},
                        "chunks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "uuid": {"type": "string", "format": "uuid"},
                                    "status": {"type": "string", "enum": ["created", "error"]},
                                    "error": {"type": "string"}
                                },
                                "required": ["uuid", "status"]
                            }
                        }
                    },
                    "required": ["created_count", "chunks"]
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
            "invalid_params", "validation_error", "creation_error", "embedding_error"
        ])

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get complete command metadata for help system.

        Returns:
            Dictionary with command metadata
        """
        error_codes = [
            {"code": "invalid_params", "description": "Invalid parameters provided", "when": "When chunks array is missing or invalid"},
            {"code": "validation_error", "description": "Chunk validation failed", "when": "When chunk data fails SemanticChunk validation"},
            {"code": "creation_error", "description": "Failed to create chunk", "when": "When vector store operation fails"},
            {"code": "embedding_error", "description": "Failed to generate embedding", "when": "When embedding service fails"}
        ]
        
        examples = {
            "success": {
                "success": True,
                "data": {
                    "created_count": 1,
                    "chunks": [{"uuid": "123e4567-e89b-12d3-a456-426614174000", "status": "created"}]
                }
            },
            "error": {
                "success": False,
                "error": {
                    "code": "validation_error",
                    "message": "Invalid chunk data: body field is required",
                    "data": {"chunk_index": 0, "field": "body"}
                }
            }
        }
        
        return super().get_metadata(error_codes, examples)

    async def execute(self, **params) -> CreateResult:
        """
        Execute upsert command with list of SemanticChunk.

        Args:
            **params: Command parameters including 'chunks' array

        Returns:
            CreateResult with creation status or ErrorResult on failure
        """
        try:
            chunks_data = params.get("chunks")
            
            if not chunks_data:
                return ErrorResult(
                    code="invalid_params",
                    message="Parameter 'chunks' is required",
                    details={"params": params}
                )
            
            if not isinstance(chunks_data, list):
                return ErrorResult(
                    code="invalid_params",
                    message="Parameter 'chunks' must be an array",
                    details={"chunks": chunks_data}
                )
            
            if len(chunks_data) == 0:
                return ErrorResult(
                    code="invalid_params",
                    message="Parameter 'chunks' cannot be empty",
                    details={"chunks": chunks_data}
                )

            # Process each chunk
            created_chunks = []
            for i, chunk_data in enumerate(chunks_data):
                try:
                    # Create SemanticChunk from data
                    semantic_chunk = SemanticChunk(**chunk_data)
                    
                    # Upsert to vector store
                    uuid = await self.vector_store_service.upsert_chunk(semantic_chunk)
                    
                    created_chunks.append({
                        "uuid": uuid,
                        "status": "created"
                    })
                    
                except Exception as e:
                    self.logger.error(f"Failed to upsert chunk at index {i}: {e}")
                    return ErrorResult(
                        code="upsert_error",
                        message=f"Failed to upsert chunk at index {i}: {e}",
                        details={"failed_index": i, "error": str(e)}
                    )

            return CreateResult(
                uuids=[chunk["uuid"] for chunk in created_chunks],
                created_count=len(created_chunks),
                metadata={"chunks": created_chunks}
            )

        except Exception as e:
            self.logger.error(f"Unexpected error in upsert: {e}")
            return ErrorResult(
                code="unexpected_error",
                message=f"Unexpected error in upsert: {e}",
                details={"error": str(e)}
            )


def make_upsert(vector_store_service) -> UpsertCommand:
    """
    Factory function to create UpsertCommand instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        Configured UpsertCommand instance
    """
    return UpsertCommand(vector_store_service)
