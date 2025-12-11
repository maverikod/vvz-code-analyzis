"""
Index Manager module for vector_store.

This module provides fast metadata indexing and search capabilities
for the vector store system.

Features:
- Fast O(1) metadata search instead of O(n) scanning
- Support for all field types (scalar, arrays, nested objects)
- Double indexing for arrays (elements + exact match)
- Atomic operations with rollback support
- Backward compatibility with existing code

Architecture:
- Base classes define the interface for index management
- Utility classes provide common operations
- Result classes standardize operation responses
- Factory functions for easy instantiation

Author: Vasiliy Zdanovskiy <vasilyvz@gmail.com>
Created: 2024-01-15
Updated: 2024-01-15
"""

from .base import (
    BaseIndexManager,
    IndexType,
    IndexOperator,
    IndexStatus,
    IndexResult,
    IndexStatsResult,
    SearchResult,
    create_index_manager,
    validate_index_config
)
from .utils import IndexUtils

__all__ = [
    "BaseIndexManager",
    "IndexType", 
    "IndexOperator",
    "IndexStatus",
    "IndexUtils",
    "IndexResult",
    "IndexStatsResult", 
    "SearchResult",
    "create_index_manager",
    "validate_index_config"
]
