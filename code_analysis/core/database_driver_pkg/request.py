"""
Base request classes for RPC database operations.

Provides abstract base classes and concrete implementations for different
types of database operations (insert, select, update, delete, transactions).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class BaseRequest(ABC):
    """Abstract base class for all RPC requests.

    All request classes must implement:
    - validate() - validate request parameters
    - to_dict() - convert to dictionary for serialization
    - from_dict() - create from dictionary (class method)
    """

    @abstractmethod
    def validate(self) -> None:
        """Validate request parameters.

        Raises:
            ValueError: If request parameters are invalid
        """
        raise NotImplementedError

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert request to dictionary for serialization.

        Returns:
            Dictionary representation of request
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> BaseRequest:
        """Create request from dictionary.

        Args:
            data: Dictionary with request data

        Returns:
            Request instance
        """
        raise NotImplementedError


@dataclass
class TableOperationRequest(BaseRequest):
    """Base class for table operation requests.

    Provides common fields for table operations (insert, update, delete, select).
    """

    table_name: str

    def validate(self) -> None:
        """Validate table operation request."""
        if not self.table_name or not isinstance(self.table_name, str):
            raise ValueError("table_name must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {"table_name": self.table_name}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TableOperationRequest:
        """Create from dictionary."""
        return cls(table_name=data.get("table_name", ""))


@dataclass
class InsertRequest(TableOperationRequest):
    """Request for insert operation."""

    data: Dict[str, Any]

    def validate(self) -> None:
        """Validate insert request."""
        super().validate()
        if not isinstance(self.data, dict):
            raise ValueError("data must be a dictionary")
        if not self.data:
            raise ValueError("data cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = super().to_dict()
        result["data"] = self.data
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InsertRequest:
        """Create from dictionary."""
        return cls(
            table_name=data.get("table_name", ""),
            data=data.get("data", {}),
        )


@dataclass
class SelectRequest(TableOperationRequest):
    """Request for select operation."""

    where: Optional[Dict[str, Any]] = None
    columns: Optional[List[str]] = None
    limit: Optional[int] = None
    offset: Optional[int] = None
    order_by: Optional[List[str]] = None

    def validate(self) -> None:
        """Validate select request."""
        super().validate()
        if self.where is not None and not isinstance(self.where, dict):
            raise ValueError("where must be a dictionary or None")
        if self.columns is not None and not isinstance(self.columns, list):
            raise ValueError("columns must be a list or None")
        if self.limit is not None and (
            not isinstance(self.limit, int) or self.limit < 0
        ):
            raise ValueError("limit must be a non-negative integer or None")
        if self.offset is not None and (
            not isinstance(self.offset, int) or self.offset < 0
        ):
            raise ValueError("offset must be a non-negative integer or None")
        if self.order_by is not None and not isinstance(self.order_by, list):
            raise ValueError("order_by must be a list or None")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = super().to_dict()
        if self.where is not None:
            result["where"] = self.where
        if self.columns is not None:
            result["columns"] = self.columns
        if self.limit is not None:
            result["limit"] = self.limit
        if self.offset is not None:
            result["offset"] = self.offset
        if self.order_by is not None:
            result["order_by"] = self.order_by
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SelectRequest:
        """Create from dictionary."""
        return cls(
            table_name=data.get("table_name", ""),
            where=data.get("where"),
            columns=data.get("columns"),
            limit=data.get("limit"),
            offset=data.get("offset"),
            order_by=data.get("order_by"),
        )


@dataclass
class UpdateRequest(TableOperationRequest):
    """Request for update operation."""

    where: Dict[str, Any]
    data: Dict[str, Any]

    def validate(self) -> None:
        """Validate update request."""
        super().validate()
        if not isinstance(self.where, dict):
            raise ValueError("where must be a dictionary")
        if not self.where:
            raise ValueError("where cannot be empty")
        if not isinstance(self.data, dict):
            raise ValueError("data must be a dictionary")
        if not self.data:
            raise ValueError("data cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = super().to_dict()
        result["where"] = self.where
        result["data"] = self.data
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UpdateRequest:
        """Create from dictionary."""
        return cls(
            table_name=data.get("table_name", ""),
            where=data.get("where", {}),
            data=data.get("data", {}),
        )


@dataclass
class DeleteRequest(TableOperationRequest):
    """Request for delete operation."""

    where: Dict[str, Any]

    def validate(self) -> None:
        """Validate delete request."""
        super().validate()
        if not isinstance(self.where, dict):
            raise ValueError("where must be a dictionary")
        if not self.where:
            raise ValueError("where cannot be empty")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = super().to_dict()
        result["where"] = self.where
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeleteRequest:
        """Create from dictionary."""
        return cls(
            table_name=data.get("table_name", ""),
            where=data.get("where", {}),
        )


@dataclass
class TransactionRequest(BaseRequest):
    """Request for transaction operation."""

    transaction_id: str
    operation: str  # "begin", "commit", "rollback"

    def validate(self) -> None:
        """Validate transaction request."""
        if not self.transaction_id or not isinstance(self.transaction_id, str):
            raise ValueError("transaction_id must be a non-empty string")
        if self.operation not in ("begin", "commit", "rollback"):
            raise ValueError("operation must be 'begin', 'commit', or 'rollback'")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "transaction_id": self.transaction_id,
            "operation": self.operation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TransactionRequest:
        """Create from dictionary."""
        return cls(
            transaction_id=data.get("transaction_id", ""),
            operation=data.get("operation", "begin"),
        )
