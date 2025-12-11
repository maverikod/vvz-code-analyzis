"""
Vector Store Commands Package.

This package contains all command implementations for the vector store API,
organized by functionality and following MCP Proxy Adapter architecture.

Features:
- CRUD operations for vector store records
- Search and filtering capabilities
- Maintenance and administration operations
- Standardized command interface
- Integration with chunk_metadata_adapter

Architecture:
- Commands organized by category (index, search, maintenance)
- Base classes for standardization
- Result classes for consistent formatting
- Validators for parameter validation
- Exception handling for error management

Author: Vector Store Team
Created: 2024-12-19
Updated: 2024-12-19
"""

# Base classes - used internally by commands
from vector_store.commands.base import BaseVectorStoreCommand
from vector_store.commands.base_result import BaseCommandResult
from vector_store.commands.command_validator import CommandValidator

# Result classes - used internally by commands
from vector_store.commands.result_classes import (
    SearchResult,
    CreateResult,
    DeleteResult,
    CountResult,
    InfoResult,
    HardDeleteResult,
    ForceDeleteResult,
    FindDuplicateUuidsResult
)

# Commands are imported directly from their modules when needed
# This package provides base classes and result classes for internal use

__all__ = [
    # Base classes
    'BaseVectorStoreCommand',
    'BaseCommandResult',
    'CommandValidator',
    
    # Result classes
    'SearchResult',
    'CreateResult',
    'DeleteResult',
    'CountResult',
    'InfoResult',
    'HardDeleteResult',
    'ForceDeleteResult',
    'FindDuplicateUuidsResult'
]
