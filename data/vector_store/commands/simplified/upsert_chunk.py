"""
Upsert chunk command for simplified API.

This command creates or updates chunk using the new simplified VectorStoreService.
It accepts SemanticChunk data in serialized form.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Dict, Any

from vector_store.exceptions import (
    InvalidParamsError, ValidationError, CommandError, CreationError,
    VectorStoreServiceError, UnexpectedError
)

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import CreateResult
from mcp_proxy_adapter.commands.result import ErrorResult
from chunk_metadata_adapter.semantic_chunk import SemanticChunk

logger = logging.getLogger(__name__)


class UpsertChunkCommand(BaseVectorStoreCommand):
    """
    Create or update chunk using simplified API.
    
    This command accepts SemanticChunk data in serialized form and uses
    the new simplified VectorStoreService.upsert() method.
    
    Parameters:
        chunk (object, required): SemanticChunk data in serialized form
            - Must contain required fields: uuid, type, body
            - All other fields are optional or auto-generated
            - See SemanticChunk for complete field definitions
    
    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "uuid": "550e8400-e29b-41d4-a716-446655440000"
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "validation_error",
                    "message": "Invalid chunk data: body field is required"
                }
            }
    
    Examples:
        # Basic chunk creation
        {
            "chunk": {
                "uuid": "550e8400-e29b-41d4-a716-446655440000",
                "type": "DocBlock",
                "body": "Sample content",
                "text": "Sample content",
                "tags": ["test"],
                "category": "test"
            }
        }
        
        # Chunk with embedding
        {
            "chunk": {
                "uuid": "550e8400-e29b-41d4-a716-446655440001",
                "type": "DocBlock", 
                "body": "Content with embedding",
                "embedding": [0.1, 0.2, 0.3, ...],
                "language": "en"
            }
        }
        
        # Chunk with all metadata
        {
            "chunk": {
                "uuid": "550e8400-e29b-41d4-a716-446655440002",
                "type": "DocBlock",
                "body": "Complete chunk example",
                "text": "Complete chunk example",
                "summary": "Short summary",
                "tags": ["example", "complete"],
                "category": "documentation",
                "language": "en",
                "title": "Example Title",
                "source_path": "/path/to/source",
                "quality_score": 0.95
            }
        }
    """

    name = "upsert_chunk"
    result_class = CreateResult

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
                "chunk": {
                    "type": "object",
                    "description": "SemanticChunk data in serialized form",
                    "properties": {
                        "uuid": {
                            "type": "string",
                            "format": "uuid",
                            "description": "Unique identifier (UUIDv4)"
                        },
                        "type": {
                            "type": "string",
                            "description": "Chunk type",
                            "enum": ["DocBlock", "CodeBlock", "Message", "Section", "Other"]
                        },
                        "body": {
                            "type": "string",
                            "description": "Original chunk text (required)",
                            "minLength": 1
                        },
                        "text": {
                            "type": "string",
                            "description": "Normalized text for search"
                        },
                        "embedding": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Embedding vector"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tags"
                        },
                        "category": {
                            "type": "string",
                            "description": "Business category"
                        },
                        "language": {
                            "type": "string",
                            "description": "Language code"
                        },
                        "title": {
                            "type": "string",
                            "description": "Title or short name"
                        },
                        "summary": {
                            "type": "string",
                            "description": "Short summary"
                        },
                        "source_path": {
                            "type": "string",
                            "description": "Path to source file"
                        },
                        "quality_score": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "description": "Quality score"
                        }
                    },
                    "required": ["uuid", "type", "body"],
                    "additionalProperties": True
                }
            },
            "required": ["chunk"],
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
                        "uuids": {
                            "type": "array",
                            "items": {"type": "string", "format": "uuid"}
                        },
                        "created_count": {"type": "integer", "minimum": 0}
                    },
                    "required": ["uuids", "created_count"]
                }
            },
            "required": ["success", "data"]
        }

    async def execute(self, chunk: Dict[str, Any]) -> CreateResult:
        """
        Execute upsert chunk command.

        Args:
            chunk: SemanticChunk data in serialized form

        Returns:
            CreateResult with UUID of created/updated chunk

        Raises:
            InvalidParamsError: If chunk parameter is missing or invalid
            ValidationError: If chunk data fails validation
            CreationError: If chunk creation fails
        """
        self._start_execution()
        
        try:
            # Validate input parameters
            if not chunk:
                raise InvalidParamsError("chunk parameter is required")
            
            if not isinstance(chunk, dict):
                raise InvalidParamsError("chunk must be an object")
            
            self.logger.debug(f"Upsert chunk: {chunk.get('uuid', 'unknown')}")
            
            # Deserialize chunk data to SemanticChunk
            try:
                semantic_chunk = SemanticChunk(**chunk)
            except Exception as e:
                raise ValidationError(f"Invalid chunk data: {str(e)}")
            
            # Use simplified API
            uuid = await self.vector_store_service.upsert(semantic_chunk)
            
            self.logger.info(f"Chunk upserted successfully: {uuid}")
            
            return CreateResult(uuids=[uuid])
            
        except (InvalidParamsError, ValidationError, CreationError) as e:
            self.logger.error(f"Upsert chunk failed: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during upsert: {e}")
            raise CreationError(f"Unexpected error: {str(e)}")
