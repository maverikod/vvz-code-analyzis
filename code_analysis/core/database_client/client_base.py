"""
Base class for database client mixins.

Declares attributes and method signatures used across mixins so that mypy
and other type checkers see them. Mixins that use rpc_client, execute,
select, insert, update, get_file, or response helpers inherit from this base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from code_analysis.core.database_driver_pkg.drivers.base import DbIdentity

from .protocol import RPCResponse
from .rpc_client import RPCClient

if TYPE_CHECKING:
    from .objects.analysis import Issue, Usage
    from .objects.class_function import Class, Function
    from .objects.file import File
    from .objects.method_import import Import, Method
    from .objects.project import Project


class _DatabaseClientBase:
    """Base declaring attributes and methods used by client mixins (for type checking).

    Actual implementations are provided by _ClientHelpersMixin, _ClientOperationsMixin,
    _ClientAPIFilesMixin, etc. DatabaseClient combines all mixins and sets rpc_client.
    """

    rpc_client: RPCClient

    def _extract_success(self, response: RPCResponse) -> bool:
        """Extract success value from RPC response. Implemented in _ClientHelpersMixin."""
        raise NotImplementedError

    def _extract_result_data(self, response: RPCResponse) -> Any:
        """Extract result data from RPC response. Implemented in _ClientHelpersMixin."""
        raise NotImplementedError

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute raw SQL. Implemented in _ClientOperationsMixin."""
        raise NotImplementedError

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Select rows from table. Implemented in _ClientOperationsMixin."""
        raise NotImplementedError

    def insert(self, table_name: str, data: Dict[str, Any]) -> Optional[DbIdentity]:
        """Insert row. Implemented in _ClientOperationsMixin."""
        raise NotImplementedError

    def update(
        self,
        table_name: str,
        where: Dict[str, Any],
        data: Dict[str, Any],
    ) -> int:
        """Update rows. Implemented in _ClientOperationsMixin."""
        raise NotImplementedError

    def delete(self, table_name: str, where: Dict[str, Any]) -> int:
        """Delete rows. Implemented in _ClientOperationsMixin."""
        raise NotImplementedError

    def get_file(self, file_id: int) -> Optional["File"]:
        """Get file by ID. Implemented in _ClientAPIFilesMixin."""
        raise NotImplementedError

    def execute_batch(
        self,
        operations: List[Tuple[str, Any]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute multiple SQL statements. Implemented in _ClientOperationsMixin."""
        raise NotImplementedError

    def begin_transaction(self) -> str:
        """Begin transaction. Implemented in _ClientTransactionsMixin."""
        raise NotImplementedError

    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit transaction. Implemented in _ClientTransactionsMixin."""
        raise NotImplementedError

    def rollback_transaction(self, transaction_id: str) -> bool:
        """Rollback transaction. Implemented in _ClientTransactionsMixin."""
        raise NotImplementedError

    def get_project(self, project_id: str) -> Optional["Project"]:
        """Get project by ID. Implemented in _ClientAPIProjectsMixin."""
        raise NotImplementedError

    def get_project_files(self, project_id: str) -> List["File"]:
        """Get files for project. Implemented in _ClientAPIFilesMixin."""
        raise NotImplementedError

    def get_class(self, class_id: int) -> Optional["Class"]:
        """Get class by ID. Implemented in _ClientAPIClassesFunctionsMixin."""
        raise NotImplementedError

    def get_file_classes(self, file_id: int) -> List["Class"]:
        """Get classes for file. Implemented in _ClientAPIClassesFunctionsMixin."""
        raise NotImplementedError

    def get_file_functions(self, file_id: int) -> List["Function"]:
        """Get functions for file. Implemented in _ClientAPIClassesFunctionsMixin."""
        raise NotImplementedError

    def get_file_imports(self, file_id: int) -> List["Import"]:
        """Get imports for file. Implemented in _ClientAPIMethodsImportsMixin."""
        raise NotImplementedError

    def get_class_methods(self, class_id: int) -> List["Method"]:
        """Get methods for class. Implemented in _ClientAPIMethodsImportsMixin."""
        raise NotImplementedError

    def get_file_issues(self, file_id: int) -> List["Issue"]:
        """Get issues for file. Implemented in _ClientAPIIssuesUsagesMixin."""
        raise NotImplementedError

    def get_file_usages(self, file_id: int) -> List["Usage"]:
        """Get usages for file. Implemented in _ClientAPIIssuesUsagesMixin."""
        raise NotImplementedError
