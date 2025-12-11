"""
Info command for vector store statistics.

Provides comprehensive information about the vector store including:
- UUID counts (total, active, deleted)
- Source ID statistics
- FAISS metrics
- Redis metrics
- Metadata manager statistics
- Cache performance metrics
- Query performance metrics
- Complexity analysis metrics
- Error statistics
- Resource usage metrics
- Business usage patterns
"""

import logging
from typing import Dict, Any

from vector_store.exceptions import CommandError

from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.result_classes import InfoResult
from mcp_proxy_adapter.commands.result import ErrorResult

logger = logging.getLogger(__name__)


class InfoCommand(BaseVectorStoreCommand):
    """
    Get comprehensive information about the vector store.
    
    Returns detailed statistics including:
    - UUID counts (total, active, deleted)
    - Source ID distribution and statistics
    - FAISS index metrics
    - Redis storage statistics
    - Metadata manager statistics
    - System configuration info
    - Cache performance metrics (hits, misses, hit rates)
    - Query performance metrics (parsing time, execution time)
    - Complexity analysis metrics (AST depth, condition counts)
    - Error statistics (validation errors, execution errors)
    - Resource usage metrics (memory usage, cache sizes)
    - Business usage patterns (field usage, operator usage)
    
    Parameters:
        None
        
    Returns:
        Success:
            {
                "success": true,
                "data": {
                    "uuid_statistics": {
                        "total_uuids": 1000,
                        "active_uuids": 950,
                        "deleted_uuids": 50,
                        "deletion_rate": 0.05
                    },
                    "source_id_statistics": {
                        "total_source_ids": 1000,
                        "unique_source_ids": 25,
                        "source_id_distribution": {"doc1": 40, "doc2": 35, ...},
                        "most_common_source_ids": [["doc1", 40], ["doc2", 35], ...]
                    },
                    "faiss_statistics": {
                        "total_vectors": 950,
                        "vector_size": 384,
                        "index_type": "IndexFlatL2",
                        "operations_since_save": 0,
                        "last_save_time": "2024-01-15T10:30:00",
                        "auto_save_enabled": true
                    },
                    "redis_statistics": {
                        "total_vector_keys": 1000,
                        "deleted_keys": 50,
                        "estimated_memory_usage_bytes": 1048576,
                        "redis_connection_healthy": true
                    },
                    "metadata_statistics": {
                        "indexed_fields": ["category", "year", "source_id"],
                        "index_statistics": {"size": 1000, "unique_values_count": 25},
                        "has_index_manager": true
                    },
                    "search_statistics": {
                        "total_records": 1000,
                        "deleted_records": 50,
                        "active_records": 950,
                        "vector_size": 384
                    },
                    "system_info": {
                        "vector_size": 384,
                        "has_embedding_service": true,
                        "has_crud_service": true,
                        "has_filter_service": true,
                        "has_maintenance_service": true
                    },
                    "cache_metrics": {
                        "query_cache": {
                            "hits": 44,
                            "misses": 1,
                            "evictions": 0,
                            "size": 3,
                            "hit_rate": 97.8
                        },
                        "filter_executor_cache": {
                            "field_cache_size": 15,
                            "comparison_cache_size": 12,
                            "total_cache_entries": 27
                        },
                        "chunk_query_cache": {
                            "ast_cached": true,
                            "validation_cached": false,
                            "parser_initialized": true,
                            "executor_initialized": true,
                            "validator_initialized": true,
                            "optimizer_initialized": true
                        }
                    },
                    "performance_metrics": {
                        "query_parsing": {
                            "average_parse_time_ms": 0.5,
                            "total_queries_parsed": 1000,
                            "parse_time_distribution": {"fast": 800, "medium": 150, "slow": 50}
                        },
                        "filter_execution": {
                            "average_execution_time_ms": 0.2,
                            "total_filters_executed": 5000,
                            "execution_time_distribution": {"fast": 4500, "medium": 400, "slow": 100}
                        }
                    },
                    "complexity_metrics": {
                        "ast_analysis": {
                            "average_max_depth": 3.2,
                            "average_total_conditions": 2.8,
                            "complexity_distribution": {"simple": 600, "medium": 300, "complex": 100}
                        },
                        "operator_usage": {
                            "AND": 1200,
                            "OR": 300,
                            "=": 800,
                            ">=": 400,
                            "intersects": 200
                        },
                        "field_usage": {
                            "type": 500,
                            "quality_score": 400,
                            "tags": 300,
                            "year": 200,
                            "status": 150
                        }
                    },
                    "error_metrics": {
                        "validation_errors": {
                            "total_queries": 1000,
                            "valid_queries": 950,
                            "invalid_queries": 50,
                            "error_rate": 5.0,
                            "error_types": {
                                "syntax_error": 20,
                                "invalid_field": 15,
                                "unsupported_operator": 10,
                                "security_violation": 5
                            }
                        },
                        "execution_errors": {
                            "total_executions": 5000,
                            "successful_executions": 4950,
                            "failed_executions": 50,
                            "error_rate": 1.0
                        }
                    },
                    "resource_metrics": {
                        "memory_usage": {
                            "query_cache_bytes": 3072,
                            "filter_executor_cache_bytes": 5400,
                            "total_cache_memory_bytes": 8472,
                            "estimated_total_memory_bytes": 50000
                        },
                        "cache_efficiency": {
                            "query_cache_hit_rate": 97.8,
                            "filter_cache_hit_rate": 95.2,
                            "overall_cache_hit_rate": 96.5
                        }
                    },
                    "business_metrics": {
                        "query_patterns": {
                            "most_common_fields": [["type", 500], ["quality_score", 400], ["tags", 300]],
                            "most_common_operators": [["=", 800], ["AND", 1200], [">=", 400]],
                            "query_complexity_trend": {"simple": 60, "medium": 30, "complex": 10}
                        },
                        "usage_statistics": {
                            "total_queries_today": 150,
                            "total_queries_this_week": 1000,
                            "peak_queries_per_hour": 25,
                            "average_queries_per_hour": 15
                        }
                    }
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "service_operation_error",
                    "message": "Failed to get vector store information",
                    "data": {"details": "..."}
                }
            }
    
    Error codes:
        | Code                    | Description                    | When
        |-------------------------|--------------------------------|-------------------
        | service_operation_error | Service operation failed       | When info gathering fails
    
    Examples:
        Success:
            {
                "success": true,
                "data": {
                    "uuid_statistics": {
                        "total_uuids": 1000,
                        "active_uuids": 950,
                        "deleted_uuids": 50,
                        "deletion_rate": 0.05
                    },
                    "source_id_statistics": {
                        "total_source_ids": 1000,
                        "unique_source_ids": 25,
                        "source_id_distribution": {"doc1": 40},
                        "most_common_source_ids": [["doc1", 40]]
                    },
                    "faiss_statistics": {
                        "total_vectors": 950,
                        "vector_size": 384,
                        "index_type": "IndexFlatL2"
                    },
                    "redis_statistics": {
                        "total_vector_keys": 1000,
                        "redis_connection_healthy": true
                    },
                    "metadata_statistics": {
                        "indexed_fields": ["category"],
                        "has_index_manager": true
                    },
                    "search_statistics": {
                        "total_records": 1000,
                        "active_records": 950
                    },
                    "system_info": {
                        "vector_size": 384,
                        "has_embedding_service": true
                    },
                    "cache_metrics": {
                        "query_cache": {
                            "hits": 44,
                            "misses": 1,
                            "hit_rate": 97.8
                        }
                    },
                    "performance_metrics": {
                        "query_parsing": {
                            "average_parse_time_ms": 0.5
                        }
                    },
                    "complexity_metrics": {
                        "ast_analysis": {
                            "average_max_depth": 3.2
                        }
                    },
                    "error_metrics": {
                        "validation_errors": {
                            "error_rate": 5.0
                        }
                    },
                    "resource_metrics": {
                        "memory_usage": {
                            "total_cache_memory_bytes": 8472
                        }
                    },
                    "business_metrics": {
                        "query_patterns": {
                            "most_common_fields": [["type", 500]]
                        }
                    }
                }
            }
        Error:
            {
                "success": false,
                "error": {
                    "code": "service_operation_error",
                    "message": "Failed to get vector store information",
                    "data": {"details": "Redis connection failed"}
                }
            }
    """
    
    name = "info"
    result_class = InfoResult

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
            "properties": {},
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
                        "uuid_statistics": {
                            "type": "object",
                            "properties": {
                                "total_uuids": {"type": "integer"},
                                "active_uuids": {"type": "integer"},
                                "deleted_uuids": {"type": "integer"},
                                "deletion_rate": {"type": "number"}
                            }
                        },
                        "source_id_statistics": {
                            "type": "object",
                            "properties": {
                                "total_source_ids": {"type": "integer"},
                                "unique_source_ids": {"type": "integer"},
                                "source_id_distribution": {"type": "object"},
                                "most_common_source_ids": {"type": "array"}
                            }
                        },
                        "faiss_statistics": {
                            "type": "object",
                            "properties": {
                                "total_vectors": {"type": "integer"},
                                "vector_size": {"type": "integer"},
                                "index_type": {"type": "string"},
                                "operations_since_save": {"type": "integer"},
                                "last_save_time": {"type": "string"},
                                "auto_save_enabled": {"type": "boolean"}
                            }
                        },
                        "redis_statistics": {
                            "type": "object",
                            "properties": {
                                "total_vector_keys": {"type": "integer"},
                                "deleted_keys": {"type": "integer"},
                                "estimated_memory_usage_bytes": {"type": "integer"},
                                "redis_connection_healthy": {"type": "boolean"}
                            }
                        },
                        "metadata_statistics": {
                            "type": "object",
                            "properties": {
                                "indexed_fields": {"type": "array"},
                                "index_statistics": {"type": "object"},
                                "has_index_manager": {"type": "boolean"}
                            }
                        },
                        "search_statistics": {
                            "type": "object",
                            "properties": {
                                "total_records": {"type": "integer"},
                                "deleted_records": {"type": "integer"},
                                "active_records": {"type": "integer"},
                                "vector_size": {"type": "integer"}
                            }
                        },
                        "system_info": {
                            "type": "object",
                            "properties": {
                                "vector_size": {"type": "integer"},
                                "has_embedding_service": {"type": "boolean"},
                                "has_crud_service": {"type": "boolean"},
                                "has_filter_service": {"type": "boolean"},
                                "has_maintenance_service": {"type": "boolean"}
                            }
                        },
                        "cache_metrics": {"type": "object"},
                        "performance_metrics": {"type": "object"},
                        "complexity_metrics": {"type": "object"},
                        "error_metrics": {"type": "object"},
                        "resource_metrics": {"type": "object"},
                        "business_metrics": {"type": "object"}
                    }
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
        return super().get_error_schema(["service_operation_error"])

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
                {"code": "service_operation_error", "description": "Service operation failed", "when": "When info gathering fails"}
            ],
            "examples": {
                "success": {
                    "success": True,
                    "data": {
                        "uuid_statistics": {
                            "total_uuids": 1000,
                            "active_uuids": 950,
                            "deleted_uuids": 50,
                            "deletion_rate": 0.05
                        },
                        "source_id_statistics": {
                            "total_source_ids": 1000,
                            "unique_source_ids": 25,
                            "source_id_distribution": {"doc1": 40},
                            "most_common_source_ids": [["doc1", 40]]
                        },
                        "faiss_statistics": {
                            "total_vectors": 950,
                            "vector_size": 384,
                            "index_type": "IndexFlatL2"
                        },
                        "redis_statistics": {
                            "total_vector_keys": 1000,
                            "redis_connection_healthy": True
                        },
                        "metadata_statistics": {
                            "indexed_fields": ["category"],
                            "has_index_manager": True
                        },
                        "search_statistics": {
                            "total_records": 1000,
                            "active_records": 950
                        },
                        "system_info": {
                            "vector_size": 384,
                            "has_embedding_service": True
                        },
                        "cache_metrics": {
                            "query_cache": {
                                "hits": 44,
                                "misses": 1,
                                "hit_rate": 97.8
                            }
                        },
                        "performance_metrics": {
                            "query_parsing": {
                                "average_parse_time_ms": 0.5
                            }
                        },
                        "complexity_metrics": {
                            "ast_analysis": {
                                "average_max_depth": 3.2
                            }
                        },
                        "error_metrics": {
                            "validation_errors": {
                                "error_rate": 5.0
                            }
                        },
                        "resource_metrics": {
                            "memory_usage": {
                                "total_cache_memory_bytes": 8472
                            }
                        },
                        "business_metrics": {
                            "query_patterns": {
                                "most_common_fields": [["type", 500]]
                            }
                        }
                    }
                },
                "error": {
                    "success": False,
                    "error": {
                        "code": "service_operation_error",
                        "message": "Failed to get vector store information",
                        "data": {"details": "Redis connection failed"}
                    }
                }
            }
        }

    async def execute(self, **params: Any) -> InfoResult:
        """
        Execute info command to get comprehensive vector store statistics.

        Args:
            **params: Command parameters (none required)

        Returns:
            InfoResult with comprehensive statistics or ErrorResult on failure
        """
        try:
            # Get comprehensive statistics from vector store service
            statistics = await self.vector_store_service.info()
            
            return InfoResult(statistics)
            
        except Exception as e:
            logger.error(f"Failed to get vector store information: {e}")
            return ErrorResult(
                code="service_operation_error",
                message=f"Failed to get vector store information: {str(e)}",
                details={"details": str(e)}
            )


def make_info_command(vector_store_service):
    """
    Factory function to create InfoCommand instance.

    Args:
        vector_store_service: Vector store service instance

    Returns:
        InfoCommand instance
    """
    return InfoCommand(vector_store_service) 