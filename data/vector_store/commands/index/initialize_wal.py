"""
Initialize WAL (Write-Ahead Log) command.

This command initializes the FAISS service with WAL replay
to restore the index state from logged operations.

Features:
- Replays all WAL logs to restore FAISS index state
- Reports number of operations replayed
- Provides WAL statistics
- Handles errors gracefully

Author: Vector Store Team
Created: 2025-01-27
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from vector_store.commands.base import Command
from vector_store.commands.base_result import BaseCommandResult
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

logger = logging.getLogger(__name__)


class InitializeWALCommand(Command):
    """
    Command to initialize FAISS service with WAL replay.
    
    Replays all Write-Ahead Log files to restore the FAISS index
    state from logged operations. This ensures data consistency
    and enables fast recovery on server startup.
    """
    
    name = "initialize_wal"
    result_class = SuccessResult
    
    def __init__(self, vector_store_service):
        """
        Initialize the command.
        
        Args:
            vector_store_service: Vector store service instance
        """
        super().__init__()
        self.vector_store_service = vector_store_service
        self.logger = logging.getLogger(__name__)
    
    async def execute(self, **params) -> SuccessResult:
        """
        Execute WAL initialization.
        
        Args:
            params: Command parameters (optional)
            
        Returns:
            SuccessResult with initialization statistics
            
        Raises:
            ErrorResult: If initialization fails
        """
        try:
            self.logger.info("Starting WAL initialization...")
            
            # Get FAISS service from vector store service
            faiss_service = self.vector_store_service.faiss_service
            if not faiss_service:
                return ErrorResult(
                    code="faiss_service_missing",
                    message="FAISS service not available",
                    details="Vector store service does not have FAISS service initialized"
                )
            
            # Initialize FAISS service with WAL replay
            operations_replayed = await faiss_service.initialize_with_wal()
            
            # Get WAL statistics
            wal_stats = faiss_service.wal_service.get_log_stats()
            
            # Prepare result data
            result_data = {
                "operations_replayed": operations_replayed,
                "wal_stats": wal_stats,
                "faiss_total_vectors": await faiss_service.count(),
                "initialization_successful": True
            }
            
            self.logger.info(f"WAL initialization completed: {operations_replayed} operations replayed")
            
            return SuccessResult(
                data=result_data,
                message=f"WAL initialization successful: {operations_replayed} operations replayed"
            )
            
        except Exception as e:
            self.logger.error(f"WAL initialization failed: {e}")
            return ErrorResult(
                code="initialization_failed",
                message="WAL initialization failed",
                details=str(e)
            )
    
    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """
        Get JSON-RPC schema for this command.
        
        Returns:
            JSON-RPC schema definition
        """
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "const": "initialize_wal"
                },
                "params": {
                    "type": "object",
                    "description": "Optional parameters for WAL initialization",
                    "additionalProperties": True
                }
            },
            "required": ["method"]
        }


def make_initialize_wal(vector_store_service) -> InitializeWALCommand:
    """
    Factory function to create InitializeWALCommand instance.
    
    Args:
        vector_store_service: Vector store service instance
        
    Returns:
        Configured InitializeWALCommand instance
    """
    return InitializeWALCommand(vector_store_service) 