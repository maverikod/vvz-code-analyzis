"""
Custom exceptions for Vector Store services.

This module defines specific exception classes for different types of errors
that can occur in the vector store system, allowing for proper error classification
and handling at higher levels.
"""

from typing import Optional, List, Any


class VectorStoreError(Exception):
    """Base exception for all vector store errors."""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class RedisConnectionError(VectorStoreError):
    """Raised when Redis connection fails."""
    
    def __init__(self, message: str, redis_url: Optional[str] = None):
        details = {"redis_url": redis_url} if redis_url else {}
        super().__init__(f"Redis connection failed: {message}", details)


class RedisOperationError(VectorStoreError):
    """Raised when Redis operation fails."""
    
    def __init__(self, operation: str, message: str, details: Optional[dict] = None):
        self.operation = operation
        details = details or {}
        details["operation"] = operation
        super().__init__(f"Redis operation '{operation}' failed: {message}", details)


class RedisPipelineError(RedisOperationError):
    """Raised when Redis pipeline operation fails."""
    
    def __init__(self, operation: str, message: str, pipeline_commands: Optional[List[str]] = None):
        details = {"pipeline_commands": pipeline_commands} if pipeline_commands else {}
        super().__init__(operation, message, details)


class RedisKeyError(RedisOperationError):
    """Raised when Redis key operation fails."""
    
    def __init__(self, operation: str, key: str, message: str):
        details = {"key": key}
        super().__init__(operation, message, details)


class ChunkValidationError(VectorStoreError):
    """Raised when chunk validation fails."""
    
    def __init__(self, message: str, chunk_uuid: Optional[str] = None, validation_errors: Optional[List[str]] = None):
        details = {
            "chunk_uuid": chunk_uuid,
            "validation_errors": validation_errors
        }
        super().__init__(f"Chunk validation failed: {message}", details)


class ChunkNotFoundError(VectorStoreError):
    """Raised when chunk is not found in storage."""
    
    def __init__(self, chunk_uuid: str, storage_type: str = "Redis"):
        details = {"chunk_uuid": chunk_uuid, "storage_type": storage_type}
        super().__init__(f"Chunk {chunk_uuid} not found in {storage_type}", details)


class ChunkSerializationError(VectorStoreError):
    """Raised when chunk serialization/deserialization fails."""
    
    def __init__(self, operation: str, message: str, chunk_uuid: Optional[str] = None):
        details = {"operation": operation, "chunk_uuid": chunk_uuid}
        super().__init__(f"Chunk serialization failed ({operation}): {message}", details)


class IndexManagerError(VectorStoreError):
    """Base exception for all index manager errors."""
    
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[dict] = None):
        self.operation = operation
        details = details or {}
        if operation:
            details["operation"] = operation
        super().__init__(f"Index manager error{f' in {operation}' if operation else ''}: {message}", details)


class IndexNotFoundError(IndexManagerError):
    """Exception raised when index is not found."""
    
    def __init__(self, field_name: str, operation: Optional[str] = None):
        details = {"field_name": field_name}
        super().__init__(f"Index for field '{field_name}' not found", operation, details)


class IndexAlreadyExistsError(IndexManagerError):
    """Exception raised when trying to create existing index."""
    
    def __init__(self, field_name: str, operation: Optional[str] = None):
        details = {"field_name": field_name}
        super().__init__(f"Index for field '{field_name}' already exists", operation, details)


class IndexOperationError(IndexManagerError):
    """Exception raised when index operation fails."""
    
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[dict] = None):
        super().__init__(f"Index operation failed: {message}", operation, details)


class IndexValidationError(IndexManagerError):
    """Exception raised when index data validation fails."""
    
    def __init__(self, message: str, field_name: Optional[str] = None, operation: Optional[str] = None):
        details = {"field_name": field_name} if field_name else {}
        super().__init__(f"Index validation failed: {message}", operation, details)


class MetadataAdapterError(VectorStoreError):
    """Raised when metadata adapter operation fails."""
    
    def __init__(self, operation: str, message: str, adapter_type: str = "SemanticChunk"):
        details = {"operation": operation, "adapter_type": adapter_type}
        super().__init__(f"Metadata adapter error ({operation}): {message}", details)


class BatchOperationError(VectorStoreError):
    """Raised when batch operation fails partially or completely."""
    
    def __init__(self, operation: str, message: str, 
                 successful_items: Optional[List[str]] = None,
                 failed_items: Optional[List[str]] = None,
                 total_items: int = 0):
        details = {
            "operation": operation,
            "successful_items": successful_items or [],
            "failed_items": failed_items or [],
            "total_items": total_items,
            "success_rate": len(successful_items or []) / total_items if total_items > 0 else 0
        }
        super().__init__(f"Batch operation '{operation}' failed: {message}", details)


class ServiceInitializationError(VectorStoreError):
    """Raised when service initialization fails."""
    
    def __init__(self, service_name: str, message: str, component: Optional[str] = None):
        details = {"service_name": service_name, "component": component}
        super().__init__(f"Service '{service_name}' initialization failed: {message}", details)


class MaintenanceOperationError(VectorStoreError):
    """Raised when maintenance operation fails."""
    
    def __init__(self, operation: str, message: str, operation_id: Optional[str] = None, details: Optional[dict] = None):
        self.operation = operation
        self.operation_id = operation_id
        details = details or {}
        details.update({
            "operation": operation,
            "operation_id": operation_id
        })
        super().__init__(f"Maintenance operation '{operation}' failed: {message}", details)


# Convenience functions for common error patterns
def create_redis_operation_error(operation: str, error: Exception, context: Optional[dict] = None) -> RedisOperationError:
    """Create a RedisOperationError from a caught exception."""
    details = context or {}
    if hasattr(error, '__dict__'):
        details.update(error.__dict__)
    return RedisOperationError(operation, str(error), details)


def create_batch_operation_error(operation: str, successful: List[str], failed: List[str], 
                                error: Exception) -> BatchOperationError:
    """Create a BatchOperationError for batch operations."""
    total = len(successful) + len(failed)
    return BatchOperationError(operation, str(error), successful, failed, total)


# FAISS-specific exceptions
class FaissError(VectorStoreError):
    """Base exception for all FAISS-related errors."""
    
    def __init__(self, message: str, operation: str = None, details: Optional[dict] = None):
        self.operation = operation
        details = details or {}
        if operation:
            details["operation"] = operation
        super().__init__(f"FAISS error{f' in {operation}' if operation else ''}: {message}", details)


class FaissVectorError(FaissError):
    """Raised when vector validation or processing fails."""
    
    def __init__(self, message: str, operation: str = None, details: Optional[dict] = None):
        super().__init__(f"Vector error: {message}", operation, details)


class FaissIndexError(FaissError):
    """Raised when FAISS index operation fails."""
    
    def __init__(self, message: str, operation: str = None, details: Optional[dict] = None):
        super().__init__(f"Index error: {message}", operation, details)


class FaissSearchError(FaissError):
    """Raised when FAISS search operation fails."""
    
    def __init__(self, message: str, operation: str = None, details: Optional[dict] = None):
        super().__init__(f"Search error: {message}", operation, details)


class FaissStorageError(FaissError):
    """Raised when FAISS storage operation fails (save/load/backup)."""
    
    def __init__(self, message: str, operation: str = None, file_path: Optional[str] = None, details: Optional[dict] = None):
        details = details or {}
        if file_path:
            details["file_path"] = file_path
        super().__init__(f"Storage error: {message}", operation, details)


class FaissBatchOperationError(FaissError):
    """Raised when FAISS batch operation fails partially or completely."""
    
    def __init__(self, operation: str, message: str,
                 successful_items: Optional[List[int]] = None,
                 failed_items: Optional[List[int]] = None,
                 total_items: int = 0):
        details = {
            "operation": operation,
            "successful_items": successful_items or [],
            "failed_items": failed_items or [],
            "total_items": total_items,
            "success_rate": len(successful_items or []) / total_items if total_items > 0 else 0
        }
        super().__init__(f"Batch operation '{operation}' failed: {message}", operation, details)


# FAISS convenience functions
def create_vector_size_error(operation: str, vector_index: int, expected_size: int, actual_size: int) -> FaissVectorError:
    """Create a FaissVectorError for vector size mismatch."""
    details = {
        "vector_index": vector_index,
        "expected_size": expected_size,
        "actual_size": actual_size
    }
    return FaissVectorError(
        f"Vector size mismatch: expected {expected_size}, got {actual_size}",
        operation,
        details
    )


def create_search_limit_error(operation: str, limit: int) -> FaissSearchError:
    """Create a FaissSearchError for invalid search limit."""
    details = {"limit": limit}
    return FaissSearchError(
        f"Invalid search limit: {limit} (must be > 0)",
        operation,
        details
    )


def create_faiss_batch_operation_error(operation: str, successful: List[int], failed: List[int], 
                                      error: Exception) -> FaissBatchOperationError:
    """Create a FaissBatchOperationError for FAISS batch operations."""
    total = len(successful) + len(failed)
    return FaissBatchOperationError(operation, str(error), successful, failed, total)


# Command-specific exceptions
class CommandError(VectorStoreError):
    """Base exception for all command errors."""
    
    def __init__(self, message: str, command_name: Optional[str] = None, details: Optional[dict] = None):
        self.command_name = command_name
        details = details or {}
        if command_name:
            details["command_name"] = command_name
        super().__init__(f"Command error{f' in {command_name}' if command_name else ''}: {message}", details)


class InvalidParamsError(CommandError):
    """Raised when command parameters are invalid."""
    
    def __init__(self, message: str, command_name: Optional[str] = None, param_name: Optional[str] = None):
        details = {"param_name": param_name} if param_name else {}
        super().__init__(f"Invalid parameters: {message}", command_name, details)


class ValidationError(CommandError):
    """Raised when data validation fails."""
    
    def __init__(self, message: str, command_name: Optional[str] = None, field_name: Optional[str] = None):
        details = {"field_name": field_name} if field_name else {}
        super().__init__(f"Validation failed: {message}", command_name, details)


class SearchError(CommandError):
    """Raised when search operation fails."""
    
    def __init__(self, message: str, search_params: Optional[dict] = None, details: Optional[dict] = None):
        details = details or {}
        if search_params:
            details["search_params"] = search_params
        super().__init__(f"Search failed: {message}", "search", details)


class CreationError(CommandError):
    """Raised when creation operation fails."""
    
    def __init__(self, message: str, item_type: str = "item", details: Optional[dict] = None):
        details = details or {}
        details["item_type"] = item_type
        super().__init__(f"Creation failed: {message}", "create", details)


class DeletionError(CommandError):
    """Raised when deletion operation fails."""
    
    def __init__(self, message: str, item_uuid: Optional[str] = None, details: Optional[dict] = None):
        details = details or {}
        if item_uuid:
            details["item_uuid"] = item_uuid
        super().__init__(f"Deletion failed: {message}", "delete", details)


class UpdateError(CommandError):
    """Raised when update operation fails."""
    
    def __init__(self, message: str, item_uuid: Optional[str] = None, details: Optional[dict] = None):
        details = details or {}
        if item_uuid:
            details["item_uuid"] = item_uuid
        super().__init__(f"Update failed: {message}", "update", details)


# Service-specific exceptions
class EmbeddingServiceError(VectorStoreError):
    """Base exception for embedding service errors."""
    
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[dict] = None):
        self.operation = operation
        details = details or {}
        if operation:
            details["operation"] = operation
        super().__init__(f"Embedding service error{f' in {operation}' if operation else ''}: {message}", details)


class EmbeddingGenerationError(EmbeddingServiceError):
    """Raised when embedding generation fails."""
    
    def __init__(self, message: str, text: Optional[str] = None, operation: Optional[str] = None):
        details = {"text": text} if text else {}
        super().__init__(f"Embedding generation failed: {message}", operation, details)


class EmbeddingValidationError(EmbeddingServiceError):
    """Raised when embedding validation fails."""
    
    def __init__(self, message: str, embedding_size: Optional[int] = None, operation: Optional[str] = None):
        details = {"embedding_size": embedding_size} if embedding_size else {}
        super().__init__(f"Embedding validation failed: {message}", operation, details)


class BM25ServiceError(VectorStoreError):
    """Base exception for BM25 service errors."""
    
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[dict] = None):
        self.operation = operation
        details = details or {}
        if operation:
            details["operation"] = operation
        super().__init__(f"BM25 service error{f' in {operation}' if operation else ''}: {message}", details)


class BM25IndexError(BM25ServiceError):
    """Raised when BM25 indexing fails."""
    
    def __init__(self, message: str, document_id: Optional[str] = None, operation: Optional[str] = None):
        details = {"document_id": document_id} if document_id else {}
        super().__init__(f"BM25 indexing failed: {message}", operation, details)


class BM25SearchError(BM25ServiceError):
    """Raised when BM25 search fails."""
    
    def __init__(self, message: str, query: Optional[str] = None, operation: Optional[str] = None):
        details = {"query": query} if query else {}
        super().__init__(f"BM25 search failed: {message}", operation, details)


class BM25ConfigurationError(BM25ServiceError):
    """Raised when BM25 configuration is invalid."""
    
    def __init__(self, message: str, config_param: Optional[str] = None, operation: Optional[str] = None):
        details = {"config_param": config_param} if config_param else {}
        super().__init__(f"BM25 configuration error: {message}", operation, details)


# Vector Store Service exceptions
class VectorStoreServiceError(VectorStoreError):
    """Base exception for vector store service errors."""
    
    def __init__(self, message: str, operation: Optional[str] = None, details: Optional[dict] = None):
        self.operation = operation
        details = details or {}
        if operation:
            details["operation"] = operation
        super().__init__(f"Vector store service error{f' in {operation}' if operation else ''}: {message}", details)


class VectorStoreSearchError(VectorStoreServiceError):
    """Raised when vector store search fails."""
    
    def __init__(self, message: str, search_query: Optional[str] = None, operation: Optional[str] = None):
        details = {"search_query": search_query} if search_query else {}
        super().__init__(f"Vector store search failed: {message}", operation, details)


class VectorStoreHybridSearchError(VectorStoreServiceError):
    """Raised when hybrid search fails."""
    
    def __init__(self, message: str, search_query: Optional[str] = None, operation: Optional[str] = None):
        details = {"search_query": search_query} if search_query else {}
        super().__init__(f"Hybrid search failed: {message}", operation, details)


class VectorStoreMetadataFilterError(VectorStoreServiceError):
    """Raised when metadata filtering fails."""
    
    def __init__(self, message: str, filter_criteria: Optional[dict] = None, operation: Optional[str] = None):
        details = {"filter_criteria": filter_criteria} if filter_criteria else {}
        super().__init__(f"Metadata filtering failed: {message}", operation, details)


# Authentication and authorization exceptions
class AuthenticationError(VectorStoreError):
    """Raised when authentication fails."""
    
    def __init__(self, message: str, auth_method: Optional[str] = None, details: Optional[dict] = None):
        details = details or {}
        if auth_method:
            details["auth_method"] = auth_method
        super().__init__(f"Authentication failed: {message}", details)


class AuthorizationError(VectorStoreError):
    """Raised when authorization fails."""
    
    def __init__(self, message: str, required_permission: Optional[str] = None, details: Optional[dict] = None):
        details = details or {}
        if required_permission:
            details["required_permission"] = required_permission
        super().__init__(f"Authorization failed: {message}", details)


class TokenValidationError(AuthenticationError):
    """Raised when token validation fails."""
    
    def __init__(self, message: str, token_type: Optional[str] = None, details: Optional[dict] = None):
        details = details or {}
        if token_type:
            details["token_type"] = token_type
        super().__init__(f"Token validation failed: {message}", "token", details)


# Configuration and initialization exceptions
class ConfigurationError(VectorStoreError):
    """Raised when configuration is invalid."""
    
    def __init__(self, message: str, config_section: Optional[str] = None, config_param: Optional[str] = None):
        details = {
            "config_section": config_section,
            "config_param": config_param
        }
        super().__init__(f"Configuration error: {message}", details)


class InitializationError(VectorStoreError):
    """Raised when system initialization fails."""
    
    def __init__(self, message: str, component: Optional[str] = None, details: Optional[dict] = None):
        details = details or {}
        if component:
            details["component"] = component
        super().__init__(f"Initialization failed: {message}", details)


# Network and connection exceptions
class ConnectionError(VectorStoreError):
    """Raised when connection fails."""
    
    def __init__(self, message: str, service_name: Optional[str] = None, url: Optional[str] = None):
        details = {
            "service_name": service_name,
            "url": url
        }
        super().__init__(f"Connection failed: {message}", details)


class TimeoutError(VectorStoreError):
    """Raised when operation times out."""
    
    def __init__(self, message: str, operation: Optional[str] = None, timeout_seconds: Optional[float] = None):
        details = {
            "operation": operation,
            "timeout_seconds": timeout_seconds
        }
        super().__init__(f"Operation timed out: {message}", details)


# Data processing exceptions
class DataProcessingError(VectorStoreError):
    """Raised when data processing fails."""
    
    def __init__(self, message: str, data_type: Optional[str] = None, operation: Optional[str] = None):
        details = {
            "data_type": data_type,
            "operation": operation
        }
        super().__init__(f"Data processing failed: {message}", details)


class SerializationError(DataProcessingError):
    """Raised when serialization/deserialization fails."""
    
    def __init__(self, message: str, data_type: Optional[str] = None, format: Optional[str] = None):
        details = {
            "data_type": data_type,
            "format": format
        }
        super().__init__(f"Serialization failed: {message}", data_type, "serialize", details)


class DeserializationError(DataProcessingError):
    """Raised when deserialization fails."""
    
    def __init__(self, message: str, data_type: Optional[str] = None, format: Optional[str] = None):
        details = {
            "data_type": data_type,
            "format": format
        }
        super().__init__(f"Deserialization failed: {message}", data_type, "deserialize", details)


# Utility exceptions
class UnexpectedError(VectorStoreError):
    """Raised when an unexpected error occurs."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None, context: Optional[dict] = None):
        details = context or {}
        if original_error:
            details["original_error"] = str(original_error)
            details["original_error_type"] = type(original_error).__name__
        super().__init__(f"Unexpected error: {message}", details)


class NotImplementedError(VectorStoreError):
    """Raised when a feature is not implemented."""
    
    def __init__(self, feature_name: str, component: Optional[str] = None):
        details = {
            "feature_name": feature_name,
            "component": component
        }
        super().__init__(f"Feature '{feature_name}' is not implemented", details)


# Convenience functions for common error patterns
def create_command_error(command_name: str, message: str, details: Optional[dict] = None) -> CommandError:
    """Create a CommandError with command name."""
    return CommandError(message, command_name, details)


def create_search_error(message: str, search_params: Optional[dict] = None) -> SearchError:
    """Create a SearchError with search parameters."""
    return SearchError(message, search_params)


def create_validation_error(message: str, field_name: Optional[str] = None) -> ValidationError:
    """Create a ValidationError with field name."""
    return ValidationError(message, field_name=field_name)


def create_unexpected_error(message: str, original_error: Optional[Exception] = None, context: Optional[dict] = None) -> UnexpectedError:
    """Create an UnexpectedError with original error and context."""
    return UnexpectedError(message, original_error, context)
