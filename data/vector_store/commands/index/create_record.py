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


class ChunkCreateCommand(BaseVectorStoreCommand):
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

    name = "chunk_create"
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
                        "properties": {
                            "body": {
                                "type": "string",
                                "description": "Original chunk text (required)",
                                "minLength": 1,
                                "maxLength": 10000
                            },
                            "text": {
                                "type": "string",
                                "description": "Normalized text for search (optional, defaults to body)",
                                "minLength": 0,
                                "maxLength": 10000
                            },
                            "type": {
                                "type": "string",
                                "description": "Chunk type (e.g., 'Draft', 'DocBlock')",
                                "enum": ["Draft", "DocBlock", "CodeBlock", "Message", "Section", "Other"]
                            },
                            "language": {
                                "type": "string",
                                "description": "Language code (e.g., 'en', 'ru', 'python')"
                            },
                            "category": {
                                "type": "string",
                                "description": "Business category (e.g., 'science', 'programming')",
                                "maxLength": 64
                            },
                            "title": {
                                "type": "string",
                                "description": "Title or short name",
                                "maxLength": 256
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of tags for classification"
                            }
                        },
                        "required": ["body"],
                        "additionalProperties": True
                    },
                    "description": "Array of chunk metadata objects for creation",
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
        Execute chunk creation command.

        Args:
            **params: Command parameters including 'chunks' array

        Returns:
            CreateResult with creation status or ErrorResult on failure
        """
        try:
            # Validate required parameters
            self.validate_required_params(params, ["chunks"])
            
            chunks_data = params["chunks"]
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

            # Process each chunk - if any fails, reject entire batch
            created_chunks = []
            for i, chunk_data in enumerate(chunks_data):
                try:
                    # Validate and create SemanticChunk
                    semantic_chunk = await self._create_semantic_chunk(chunk_data, i)
                    
                    # Save to vector store
                    uuid = await self._save_chunk(semantic_chunk)
                    
                    created_chunks.append({
                        "uuid": uuid,
                        "status": "created"
                    })
                    
                except ValidationError as e:
                    # Log error and reject entire batch
                    self.logger.error(f"Validation failed for chunk at index {i}: {e}")
                    return ErrorResult(
                        code="validation_error",
                        message=str(e),
                        details={"failed_index": i, "total_count": len(chunks_data), "error": str(e)}
                    )
                except CreationError as e:
                    # Log error and reject entire batch
                    self.logger.error(f"Creation failed for chunk at index {i}: {e}")
                    return ErrorResult(
                        code="creation_error",
                        message=str(e),
                        details={"failed_index": i, "total_count": len(chunks_data), "error": str(e)}
                    )
                except Exception as e:
                    # Log error and reject entire batch
                    self.logger.error(f"Unexpected error creating chunk at index {i}: {e}")
                    return ErrorResult(
                        code="unexpected_error",
                        message=f"Unexpected error creating chunk at index {i}: {e}",
                        details={"failed_index": i, "total_count": len(chunks_data), "error": str(e)}
                    )

            return CreateResult(
                uuids=[chunk["uuid"] for chunk in created_chunks if chunk["status"] == "created"],
                created_count=len(created_chunks),
                metadata={"chunks": created_chunks}
            )

        except (InvalidParamsError, ValidationError) as e:
            return ErrorResult(
                code="validation_error",
                message=str(e),
                details={"chunks": chunks_data if 'chunks_data' in locals() else None}
            )
        except CreationError as e:
            return ErrorResult(
                code="creation_error",
                message=str(e),
                details={"chunks": chunks_data if 'chunks_data' in locals() else None}
            )
        except Exception as e:
            self.logger.error(f"Unexpected error in chunk creation: {e}")
            return ErrorResult(
                code="unexpected_error",
                message=f"Unexpected error in chunk creation: {e}",
                details={"chunks": chunks_data if 'chunks_data' in locals() else None}
            )

    async def _create_semantic_chunk(self, chunk_data: Dict[str, Any], index: int) -> SemanticChunk:
        """
        Create SemanticChunk from chunk data.

        Args:
            chunk_data: Raw chunk data
            index: Index of chunk in array

        Returns:
            Validated SemanticChunk

        Raises:
            ValidationError: If chunk validation fails
        """
        try:
            # Validate required fields
            if "body" not in chunk_data or not chunk_data["body"]:
                raise ValidationError(f"Chunk at index {index}: 'body' field is required")

            # Debug: Check if embedding is present
            if "embedding" in chunk_data:
                self.logger.info(f"Embedding found in chunk_data: {len(chunk_data['embedding'])} values")
            else:
                self.logger.info("No embedding found in chunk_data")

            # Get all possible fields from SemanticChunk using model fields
            # Instead of to_flat_dict which skips None values
            from chunk_metadata_adapter.utils import to_flat_dict
            from chunk_metadata_adapter.data_types import ChunkType, ChunkRole, ChunkStatus, BlockType, LanguageEnum
            
            # Get all possible fields directly from SemanticChunk model fields
            # This ensures we get ALL fields, including those with None values
            all_possible_fields = set(SemanticChunk.model_fields.keys())
            
            # Filter chunk_data to only include valid SemanticChunk fields
            # This ensures we pass all provided fields that are valid for SemanticChunk
            chunk_kwargs = {}
            for field_name, value in chunk_data.items():
                if field_name in all_possible_fields:
                    chunk_kwargs[field_name] = value
                else:
                    # Log unknown fields for debugging
                    self.logger.debug(f"Unknown field '{field_name}' in chunk_data at index {index}")
            
            # Debug: Log final chunk_kwargs
            self.logger.info(f"🔍 DEBUG: Final chunk_kwargs: {chunk_kwargs}")
            
            # Add UUID if provided, otherwise generate new one
            if "uuid" in chunk_data and chunk_data["uuid"] and chunk_data["uuid"] != ChunkId.empty_uuid4():
                chunk_kwargs["uuid"] = chunk_data["uuid"]
                self.logger.info(f"Using provided UUID: {chunk_data['uuid']}")
            else:
                # Generate unique UUID for this chunk
                new_uuid = str(uuid.uuid4())
                chunk_kwargs["uuid"] = new_uuid
                self.logger.info(f"Generated new UUID: {new_uuid}")
            
            # Handle embedding: validate if provided, generate if missing
            if "embedding" in chunk_data:
                if chunk_data["embedding"]:
                    # Validate provided embedding
                    embedding = chunk_data["embedding"]
                    if not isinstance(embedding, list):
                        raise ValidationError(f"Chunk at index {index}: embedding must be a list of floats")
                    if len(embedding) != 384:  # Expected dimension
                        raise ValidationError(f"Chunk at index {index}: embedding must have 384 dimensions, got {len(embedding)}")
                    chunk_kwargs["embedding"] = embedding
                    self.logger.info(f"Using provided embedding: {len(embedding)} values")
                else:
                    # Empty embedding provided - generate new one
                    if hasattr(self.vector_store_service, 'embedding_service') and self.vector_store_service.embedding_service:
                        try:
                            text_for_embedding = chunk_kwargs.get("text") or chunk_kwargs.get("body")
                            if text_for_embedding:
                                embedding = await self.vector_store_service.embedding_service.get_embedding(text_for_embedding)
                                chunk_kwargs["embedding"] = embedding
                                self.logger.info(f"Generated embedding for chunk: {len(embedding)} values")
                            else:
                                self.logger.warning("No text available for embedding generation")
                        except EmbeddingGenerationError as e:
                            self.logger.error(f"Failed to generate embedding for chunk: {e}")
                            raise e
                        except Exception as e:
                            self.logger.error(f"Unexpected error generating embedding: {e}")
                            raise EmbeddingGenerationError(f"Failed to generate embedding for chunk: {e}", text=text_for_embedding)
                    else:
                        raise ValidationError(f"Chunk at index {index}: Embedding service not available")
            else:
                # No embedding provided - generate automatically
                if hasattr(self.vector_store_service, 'embedding_service') and self.vector_store_service.embedding_service:
                    try:
                        text_for_embedding = chunk_kwargs.get("text") or chunk_kwargs.get("body")
                        if text_for_embedding:
                            embedding = await self.vector_store_service.embedding_service.get_embedding(text_for_embedding)
                            chunk_kwargs["embedding"] = embedding
                            self.logger.info(f"Generated embedding for chunk: {len(embedding)} values")
                        else:
                            self.logger.warning("No text available for embedding generation")
                    except EmbeddingGenerationError as e:
                        self.logger.error(f"Failed to generate embedding for chunk: {e}")
                        raise e
                    except Exception as e:
                        self.logger.error(f"Unexpected error generating embedding: {e}")
                        raise EmbeddingGenerationError(f"Failed to generate embedding for chunk: {e}", text=text_for_embedding)
                else:
                    raise ValidationError(f"Chunk at index {index}: Embedding service not available")
            
            # Create semantic chunk directly
            semantic_chunk = SemanticChunk(**chunk_kwargs)
            
            # Debug: Check if embedding is in semantic_chunk after creation
            if hasattr(semantic_chunk, 'embedding') and semantic_chunk.embedding:
                self.logger.info(f"Embedding found in semantic_chunk after creation: {len(semantic_chunk.embedding)} values")
            else:
                self.logger.info("No embedding found in semantic_chunk after creation")

            # Debug: Check if embedding is in semantic_chunk
            if hasattr(semantic_chunk, 'embedding') and semantic_chunk.embedding:
                self.logger.info(f"Embedding found in semantic_chunk: {len(semantic_chunk.embedding)} values")
            else:
                self.logger.info("No embedding found in semantic_chunk")

            return semantic_chunk

        except ValidationError as e:
            raise e
        except EmbeddingGenerationError as e:
            raise e
        except Exception as e:
            raise ValidationError(f"Chunk at index {index}: {e}")

    async def _save_chunk(self, semantic_chunk: SemanticChunk) -> str:
        """
        Save semantic chunk to vector store.

        Args:
            semantic_chunk: Validated semantic chunk

        Returns:
            UUID of created chunk

        Raises:
            CommandError: If save operation fails
        """
        try:
           # Save to vector store using upsert_chunk method
            uuid = await self.vector_store_service.upsert_chunk(semantic_chunk)
            
            return uuid

        except VectorStoreServiceError as e:
            raise CreationError(f"Failed to save chunk: {e}", item_type="chunk")
        except Exception as e:
            raise CreationError(f"Failed to save chunk: {e}", item_type="chunk")


def make_chunk_create(vector_store_service) -> ChunkCreateCommand:
    """
    Factory function to create ChunkCreateCommand instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        Configured ChunkCreateCommand instance
    """
    return ChunkCreateCommand(vector_store_service)
