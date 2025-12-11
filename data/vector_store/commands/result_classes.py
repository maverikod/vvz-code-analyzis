"""
Standard result classes for vector store commands.

This module provides standard result classes for different types
of vector store operations with proper formatting and validation.

Features:
- Search result formatting
- Create/Update result formatting
- Delete result formatting
- Error result formatting
- Metadata support for all results

Architecture:
- Inherits from BaseCommandResult
- Provides specific formatting for each operation type
- Includes performance metrics and metadata
- Supports validation and serialization

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

from typing import Dict, List, Any, Optional
from vector_store.commands.base_result import BaseCommandResult


class SearchResult(BaseCommandResult):
    """
    Result class for search operations.
    
    Provides standardized formatting for search results with
    support for pagination, relevance scores, and metadata.
    
    Features:
    - Chunk result formatting
    - Relevance score inclusion
    - Pagination metadata
    - Search performance metrics
    """
    
    def __init__(
        self,
        chunks: List[Dict[str, Any]],
        total_count: Optional[int] = None,
        search_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize search result.
        
        Args:
            chunks: List of found chunks
            total_count: Total number of matching chunks
            search_time: Time taken for search in seconds
            metadata: Additional search metadata
        """
        data = {
            "chunks": chunks,
            "total_count": total_count or len(chunks),
            "search_time": search_time
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for search result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "chunks": {
                            "type": "array",
                            "items": {"type": "object"}
                        },
                        "total_count": {"type": "integer"},
                        "search_time": {"type": "number"}
                    }
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchResult':
        """
        Create search result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            SearchResult instance
        """
        result_data = data.get("data", {})
        return cls(
            chunks=result_data.get("chunks", []),
            total_count=result_data.get("total_count"),
            search_time=result_data.get("search_time"),
            metadata=data.get("metadata")
        )


class CreateResult(BaseCommandResult):
    """
    Result class for create operations.
    
    Provides standardized formatting for create results with
    UUIDs of created records and creation metadata.
    
    Features:
    - Created record UUIDs
    - Creation timestamp
    - Validation results
    - Performance metrics
    """
    
    def __init__(
        self,
        uuids: List[str],
        created_count: Optional[int] = None,
        creation_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize create result.
        
        Args:
            uuids: List of created record UUIDs
            created_count: Number of successfully created records
            creation_time: Time taken for creation in seconds
            metadata: Additional creation metadata
        """
        data = {
            "uuids": uuids,
            "created_count": created_count or len(uuids),
            "creation_time": creation_time
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for create result validation.
        
        Returns:
            JSON schema dictionary
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
                            "items": {"type": "string"}
                        },
                        "created_count": {"type": "integer"},
                        "creation_time": {"type": "number"}
                    }
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CreateResult':
        """
        Create create result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            CreateResult instance
        """
        result_data = data.get("data", {})
        return cls(
            uuids=result_data.get("uuids", []),
            created_count=result_data.get("created_count"),
            creation_time=result_data.get("creation_time"),
            metadata=data.get("metadata")
        )


class DeleteResult(BaseCommandResult):
    """
    Result class for delete operations.
    
    Provides standardized formatting for delete results with
    UUIDs of deleted records and deletion metadata.
    
    Features:
    - Deleted record UUIDs
    - Deletion timestamp
    - Soft/Hard delete information
    - Performance metrics
    """
    
    def __init__(
        self,
        deleted_uuids: List[str],
        deleted_count: Optional[int] = None,
        deletion_time: Optional[float] = None,
        soft_delete: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize delete result.
        
        Args:
            deleted_uuids: List of deleted record UUIDs
            deleted_count: Number of successfully deleted records
            deletion_time: Time taken for deletion in seconds
            soft_delete: Whether soft delete was used
            metadata: Additional deletion metadata
        """
        data = {
            "deleted_uuids": deleted_uuids,
            "deleted_count": deleted_count or len(deleted_uuids),
            "deletion_time": deletion_time,
            "soft_delete": soft_delete
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for delete result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "deleted_uuids": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "deleted_count": {"type": "integer"},
                        "deletion_time": {"type": "number"},
                        "soft_delete": {"type": "boolean"}
                    }
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeleteResult':
        """
        Create delete result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            DeleteResult instance
        """
        result_data = data.get("data", {})
        return cls(
            deleted_uuids=result_data.get("deleted_uuids", []),
            deleted_count=result_data.get("deleted_count"),
            deletion_time=result_data.get("deletion_time"),
            soft_delete=result_data.get("soft_delete", True),
            metadata=data.get("metadata")
        )


class CountResult(BaseCommandResult):
    """
    Result class for count operations.
    
    Provides standardized formatting for count results with
    record counts and filtering information.
    
    Features:
    - Total record count
    - Filtered count
    - Count metadata
    - Performance metrics
    """
    
    def __init__(
        self,
        count: int,
        total_count: Optional[int] = None,
        count_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize count result.
        
        Args:
            count: Number of records matching criteria
            total_count: Total number of records in system
            count_time: Time taken for counting in seconds
            metadata: Additional count metadata
        """
        data = {
            "count": count,
            "total_count": total_count,
            "count_time": count_time
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for count result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "total_count": {"type": "integer"},
                        "count_time": {"type": "number"}
                    }
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CountResult':
        """
        Create count result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            CountResult instance
        """
        result_data = data.get("data", {})
        return cls(
            count=result_data.get("count", 0),
            total_count=result_data.get("total_count"),
            count_time=result_data.get("count_time"),
            metadata=data.get("metadata")
        )


class InfoResult(BaseCommandResult):
    """
    Result class for info operations.
    
    Provides standardized formatting for info results with
    system information and statistics.
    
    Features:
    - System statistics
    - Configuration information
    - Performance metrics
    - Health status
    """
    
    def __init__(
        self,
        info: Dict[str, Any],
        info_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize info result.
        
        Args:
            info: System information dictionary
            info_time: Time taken for info collection in seconds
            metadata: Additional info metadata
        """
        data = {
            "info": info,
            "info_time": info_time
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for info result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "info": {
                            "type": "object",
                            "additionalProperties": True
                        },
                        "info_time": {"type": "number"}
                    }
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InfoResult':
        """
        Create info result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            InfoResult instance
        """
        result_data = data.get("data", {})
        return cls(
            info=result_data.get("info", {}),
            info_time=result_data.get("info_time"),
            metadata=data.get("metadata")
        )


class HardDeleteResult(BaseCommandResult):
    """
    Result class for hard delete operations.
    
    Provides standardized formatting for hard delete results with
    physical deletion confirmation and metadata.
    
    Features:
    - Deletion confirmation
    - Deleted UUIDs list
    - Deletion time tracking
    - Physical removal confirmation
    """
    
    def __init__(
        self,
        deleted_count: int,
        deleted_uuids: List[str],
        deletion_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize hard delete result.
        
        Args:
            deleted_count: Number of successfully deleted records
            deleted_uuids: List of deleted UUIDs
            deletion_time: Time taken for deletion in seconds
            metadata: Additional deletion metadata
        """
        data = {
            "deleted_count": deleted_count,
            "deleted_uuids": deleted_uuids,
            "deletion_time": deletion_time
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for hard delete result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "deleted_count": {"type": "integer"},
                        "deleted_uuids": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "deletion_time": {"type": "number"}
                    },
                    "required": ["deleted_count", "deleted_uuids"]
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HardDeleteResult':
        """
        Create hard delete result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            HardDeleteResult instance
        """
        result_data = data.get("data", {})
        return cls(
            deleted_count=result_data.get("deleted_count", 0),
            deleted_uuids=result_data.get("deleted_uuids", []),
            deletion_time=result_data.get("deletion_time"),
            metadata=data.get("metadata")
        )


class ForceDeleteResult(BaseCommandResult):
    """
    Result class for force delete operations.
    
    Provides standardized formatting for force delete results with
    detailed deletion statistics and error tracking.
    
    Features:
    - Deletion statistics
    - Error tracking
    - Not found tracking
    - Detailed result breakdown
    """
    
    def __init__(
        self,
        deleted: int,
        not_found: int,
        errors: int,
        errors_uuids: List[str],
        deletion_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize force delete result.
        
        Args:
            deleted: Number of successfully deleted records
            not_found: Number of records not found
            errors: Number of records with deletion errors
            errors_uuids: List of UUIDs that failed to delete
            deletion_time: Time taken for deletion in seconds
            metadata: Additional deletion metadata
        """
        data = {
            "deleted": deleted,
            "not_found": not_found,
            "errors": errors,
            "errors_uuids": errors_uuids,
            "deletion_time": deletion_time
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for force delete result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "deleted": {"type": "integer"},
                        "not_found": {"type": "integer"},
                        "errors": {"type": "integer"},
                        "errors_uuids": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "deletion_time": {"type": "number"}
                    },
                    "required": ["deleted", "not_found", "errors", "errors_uuids"]
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ForceDeleteResult':
        """
        Create force delete result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            ForceDeleteResult instance
        """
        result_data = data.get("data", {})
        return cls(
            deleted=result_data.get("deleted", 0),
            not_found=result_data.get("not_found", 0),
            errors=result_data.get("errors", 0),
            errors_uuids=result_data.get("errors_uuids", []),
            deletion_time=result_data.get("deletion_time"),
            metadata=data.get("metadata")
        )


class FindDuplicateUuidsResult(BaseCommandResult):
    """
    Result class for find duplicate UUIDs operations.
    
    Provides standardized formatting for duplicate UUID scan results with
    detailed duplicate information and metadata.
    
    Features:
    - Duplicate UUID identification
    - Record details for duplicates
    - Scan statistics
    - Data integrity information
    """
    
    def __init__(
        self,
        duplicate_uuids: List[Dict[str, Any]],
        scan_time: Optional[float] = None,
        total_records_scanned: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize find duplicate UUIDs result.
        
        Args:
            duplicate_uuids: List of duplicate UUIDs with their records
            scan_time: Time taken for scan in seconds
            total_records_scanned: Total number of records scanned
            metadata: Additional scan metadata
        """
        data = {
            "duplicate_uuids": duplicate_uuids,
            "scan_time": scan_time,
            "total_records_scanned": total_records_scanned
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for find duplicate UUIDs result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
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
                            }
                        },
                        "scan_time": {"type": "number"},
                        "total_records_scanned": {"type": "integer"}
                    },
                    "required": ["duplicate_uuids"]
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FindDuplicateUuidsResult':
        """
        Create find duplicate UUIDs result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            FindDuplicateUuidsResult instance
        """
        result_data = data.get("data", {})
        return cls(
            duplicate_uuids=result_data.get("duplicate_uuids", []),
            scan_time=result_data.get("scan_time"),
            total_records_scanned=result_data.get("total_records_scanned"),
            metadata=data.get("metadata")
        ) 


class CleanFaissOrphansResult(BaseCommandResult):
    """
    Result class for clean FAISS orphans operations.
    
    Provides standardized formatting for FAISS orphan cleanup results with
    detailed cleanup statistics and metadata.
    
    Features:
    - Orphan vector cleanup
    - Cleanup statistics
    - Performance metrics
    - Data integrity information
    """
    
    def __init__(
        self,
        removed: int,
        cleanup_time: Optional[float] = None,
        total_vectors_checked: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize clean FAISS orphans result.
        
        Args:
            removed: Number of orphan vectors removed
            cleanup_time: Time taken for cleanup in seconds
            total_vectors_checked: Total number of vectors checked
            metadata: Additional cleanup metadata
        """
        data = {
            "removed": removed,
            "cleanup_time": cleanup_time,
            "total_vectors_checked": total_vectors_checked
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for clean FAISS orphans result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "removed": {"type": "integer", "minimum": 0},
                        "cleanup_time": {"type": "number"},
                        "total_vectors_checked": {"type": "integer"}
                    },
                    "required": ["removed"]
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CleanFaissOrphansResult':
        """
        Create clean FAISS orphans result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            CleanFaissOrphansResult instance
        """
        result_data = data.get("data", {})
        return cls(
            removed=result_data.get("removed", 0),
            cleanup_time=result_data.get("cleanup_time"),
            total_vectors_checked=result_data.get("total_vectors_checked"),
            metadata=data.get("metadata")
        )


class ReindexMissingEmbeddingsResult(BaseCommandResult):
    """
    Result class for reindex missing embeddings operations.
    
    Provides standardized formatting for reindexing results with
    detailed statistics about updated, skipped, and failed records.
    
    Features:
    - Reindexing statistics
    - Error tracking
    - Performance metrics
    - Data integrity information
    """
    
    def __init__(
        self,
        updated: int,
        skipped: int,
        errors: int,
        errors_uuids: List[str],
        reindex_time: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize reindex missing embeddings result.
        
        Args:
            updated: Number of records successfully updated
            skipped: Number of records skipped
            errors: Number of records with errors
            errors_uuids: List of UUIDs with errors
            reindex_time: Time taken for reindexing in seconds
            metadata: Additional reindexing metadata
        """
        data = {
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "errors_uuids": errors_uuids,
            "reindex_time": reindex_time
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for reindex missing embeddings result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "updated": {"type": "integer", "minimum": 0},
                        "skipped": {"type": "integer", "minimum": 0},
                        "errors": {"type": "integer", "minimum": 0},
                        "errors_uuids": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "reindex_time": {"type": "number"}
                    },
                    "required": ["updated", "skipped", "errors", "errors_uuids"]
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ReindexMissingEmbeddingsResult':
        """
        Create reindex missing embeddings result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            ReindexMissingEmbeddingsResult instance
        """
        result_data = data.get("data", {})
        return cls(
            updated=result_data.get("updated", 0),
            skipped=result_data.get("skipped", 0),
            errors=result_data.get("errors", 0),
            errors_uuids=result_data.get("errors_uuids", []),
            reindex_time=result_data.get("reindex_time"),
            metadata=data.get("metadata")
        )


class FullReindexResult(BaseCommandResult):
    """
    Result class for full reindex operations.
    
    Provides standardized formatting for full reindexing results with
    detailed statistics about total chunks, processed, and failed records.
    
    Features:
    - Full reindexing statistics
    - Error tracking
    - Performance metrics
    - Duration tracking
    """
    
    def __init__(
        self,
        total_chunks: int = 0,
        processed: int = 0,
        failed: int = 0,
        failed_uuids: List[str] = None,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize full reindex result.
        
        Args:
            total_chunks: Total number of chunks found in Redis
            processed: Number of chunks successfully processed
            failed: Number of chunks that failed to process
            failed_uuids: List of UUIDs that failed to process
            duration_seconds: Time taken for reindexing in seconds
            metadata: Additional reindexing metadata
        """
        if failed_uuids is None:
            failed_uuids = []
            
        data = {
            "total_chunks": total_chunks,
            "processed": processed,
            "failed": failed,
            "failed_uuids": failed_uuids,
            "duration_seconds": duration_seconds
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for full reindex result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "total_chunks": {"type": "integer", "minimum": 0},
                        "processed": {"type": "integer", "minimum": 0},
                        "failed": {"type": "integer", "minimum": 0},
                        "failed_uuids": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "duration_seconds": {"type": "number"}
                    },
                    "required": ["total_chunks", "processed", "failed", "failed_uuids", "duration_seconds"]
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FullReindexResult':
        """
        Create full reindex result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            FullReindexResult instance
        """
        result_data = data.get("data", {})
        return cls(
            total_chunks=result_data.get("total_chunks", 0),
            processed=result_data.get("processed", 0),
            failed=result_data.get("failed", 0),
            failed_uuids=result_data.get("failed_uuids", []),
            duration_seconds=result_data.get("duration_seconds"),
            metadata=data.get("metadata")
        )


class IntegrityCheckResult(BaseCommandResult):
    """
    Result class for data integrity check operations.
    
    Provides standardized formatting for integrity check results with
    detailed statistics about Redis and FAISS data consistency.
    
    Features:
    - Redis vs FAISS count comparison
    - Discrepancy detection
    - Reindexing status
    - Performance metrics
    """
    
    def __init__(
        self,
        redis_count: int,
        faiss_count: int,
        discrepancy_found: bool,
        reindexed: bool,
        duration_seconds: Optional[float] = None,
        details: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize integrity check result.
        
        Args:
            redis_count: Number of records in Redis
            faiss_count: Number of vectors in FAISS
            discrepancy_found: Whether discrepancy was found
            reindexed: Whether reindexing was performed
            duration_seconds: Time taken for check in seconds
            details: Detailed information about the operation
            metadata: Additional integrity check metadata
        """
        data = {
            "redis_count": redis_count,
            "faiss_count": faiss_count,
            "discrepancy_found": discrepancy_found,
            "reindexed": reindexed,
            "duration_seconds": duration_seconds,
            "details": details
        }
        
        super().__init__(data=data, metadata=metadata)
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for integrity check result validation.
        
        Returns:
            JSON schema dictionary
        """
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "data": {
                    "type": "object",
                    "properties": {
                        "redis_count": {"type": "integer", "minimum": 0},
                        "faiss_count": {"type": "integer", "minimum": 0},
                        "discrepancy_found": {"type": "boolean"},
                        "reindexed": {"type": "boolean"},
                        "duration_seconds": {"type": "number"},
                        "details": {"type": "string"}
                    },
                    "required": ["redis_count", "faiss_count", "discrepancy_found", "reindexed", "duration_seconds", "details"]
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True
                }
            },
            "required": ["success", "data"]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IntegrityCheckResult':
        """
        Create integrity check result instance from dictionary.
        
        Args:
            data: Dictionary with result data
            
        Returns:
            IntegrityCheckResult instance
        """
        result_data = data.get("data", {})
        return cls(
            redis_count=result_data.get("redis_count", 0),
            faiss_count=result_data.get("faiss_count", 0),
            discrepancy_found=result_data.get("discrepancy_found", False),
            reindexed=result_data.get("reindexed", False),
            duration_seconds=result_data.get("duration_seconds"),
            details=result_data.get("details"),
            metadata=data.get("metadata")
        )