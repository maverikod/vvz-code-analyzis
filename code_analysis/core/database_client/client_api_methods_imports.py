"""
Method and Import operations API methods for database client.

Provides object-oriented API methods for Method, Import operations and relationship navigation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .objects.class_function import Class
from .objects.method_import import Import, Method
from .objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)


class _ClientAPIMethodsImportsMixin:
    """Mixin class with Method, Import operation and relationship navigation methods."""

    # ============================================================================
    # Method Operations
    # ============================================================================

    def create_method(self, method: Method) -> Method:
        """Create new method in database.

        Args:
            method: Method object to create

        Returns:
            Created Method object with ID and updated timestamps

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If method data is invalid
        """
        table_name = get_table_name_for_object(method)
        if table_name is None:
            raise ValueError("Unknown table for Method object")

        data = object_to_db_row(method)
        self.insert(table_name, data)

        # Fetch created method
        rows = self.select(
            table_name,
            where={
                "class_id": method.class_id,
                "name": method.name,
                "line": method.line,
            },
        )
        if not rows:
            raise ValueError(
                f"Failed to create method {method.name} in class {method.class_id}"
            )

        return db_row_to_object(rows[0], Method)

    def get_method(self, method_id: int) -> Optional[Method]:
        """Get method by ID.

        Args:
            method_id: Method identifier

        Returns:
            Method object or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("methods", where={"id": method_id})
        if not rows:
            return None

        return db_row_to_object(rows[0], Method)

    def get_class_methods(self, class_id: int) -> List[Method]:
        """Get all methods for a class.

        Args:
            class_id: Class identifier

        Returns:
            List of Method objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("methods", where={"class_id": class_id}, order_by=["line"])
        return db_rows_to_objects(rows, Method)

    def search_methods(
        self,
        class_id: Optional[int] = None,
        name: Optional[str] = None,
        is_abstract: Optional[bool] = None,
    ) -> List[Method]:
        """Search methods by criteria.

        Args:
            class_id: Class identifier (optional)
            name: Method name pattern (optional)
            is_abstract: Filter by abstract methods (optional)

        Returns:
            List of Method objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        # Use SQL for LIKE pattern matching when name is specified
        if name:
            sql = "SELECT * FROM methods WHERE 1=1"
            params = []
            if class_id:
                sql += " AND class_id = ?"
                params.append(class_id)
            sql += " AND name LIKE ?"
            params.append(f"%{name}%")
            if is_abstract is not None:
                sql += " AND is_abstract = ?"
                params.append(1 if is_abstract else 0)
            sql += " ORDER BY line"
            result = self.execute(sql, tuple(params))
            rows = result.get("data", [])
        else:
            where = {}
            if class_id:
                where["class_id"] = class_id
            if is_abstract is not None:
                where["is_abstract"] = 1 if is_abstract else 0
            rows = self.select("methods", where=where, order_by=["line"])

        return db_rows_to_objects(rows, Method)

    # ============================================================================
    # Import Operations
    # ============================================================================

    def create_import(self, import_obj: Import) -> Import:
        """Create new import in database.

        Args:
            import_obj: Import object to create

        Returns:
            Created Import object with ID and updated timestamps

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If import data is invalid
        """
        table_name = get_table_name_for_object(import_obj)
        if table_name is None:
            raise ValueError("Unknown table for Import object")

        data = object_to_db_row(import_obj)
        self.insert(table_name, data)

        # Fetch created import
        rows = self.select(
            table_name,
            where={
                "file_id": import_obj.file_id,
                "name": import_obj.name,
                "line": import_obj.line,
            },
        )
        if not rows:
            raise ValueError(
                f"Failed to create import {import_obj.name} in file {import_obj.file_id}"
            )

        return db_row_to_object(rows[0], Import)

    def get_import(self, import_id: int) -> Optional[Import]:
        """Get import by ID.

        Args:
            import_id: Import identifier

        Returns:
            Import object or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("imports", where={"id": import_id})
        if not rows:
            return None

        return db_row_to_object(rows[0], Import)

    def get_file_imports(self, file_id: int) -> List[Import]:
        """Get all imports for a file.

        Args:
            file_id: File identifier

        Returns:
            List of Import objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("imports", where={"file_id": file_id}, order_by=["line"])
        return db_rows_to_objects(rows, Import)

    def search_imports(
        self,
        project_id: Optional[str] = None,
        name: Optional[str] = None,
        module: Optional[str] = None,
    ) -> List[Import]:
        """Search imports by criteria.

        Args:
            project_id: Project identifier (optional)
            name: Import name pattern (optional)
            module: Module name pattern (optional)

        Returns:
            List of Import objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        if project_id:
            sql = """
                SELECT i.* FROM imports i
                JOIN files f ON i.file_id = f.id
                WHERE f.project_id = ?
            """
            params = [project_id]
            if name:
                sql += " AND i.name LIKE ?"
                params.append(f"%{name}%")
            if module:
                sql += " AND i.module LIKE ?"
                params.append(f"%{module}%")
            sql += " ORDER BY i.line"
            result = self.execute(sql, tuple(params))
            rows = result.get("data", [])
        else:
            # Use SQL for LIKE pattern matching when project_id is not specified
            if name or module:
                sql = "SELECT * FROM imports WHERE 1=1"
                params = []
                if name:
                    sql += " AND name LIKE ?"
                    params.append(f"%{name}%")
                if module:
                    sql += " AND module LIKE ?"
                    params.append(f"%{module}%")
                sql += " ORDER BY line"
                result = self.execute(sql, tuple(params))
                rows = result.get("data", [])
            else:
                rows = self.select("imports", order_by=["line"])

        return db_rows_to_objects(rows, Import)

    # ============================================================================
    # Relationship Navigation
    # ============================================================================

    def get_class_with_methods(
        self, class_id: int
    ) -> Tuple[Optional[Class], List[Method]]:
        """Get class with all its methods.

        Args:
            class_id: Class identifier

        Returns:
            Tuple of (Class object or None, List of Method objects)

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        class_obj = self.get_class(class_id)
        if class_obj is None:
            return None, []

        methods = self.get_class_methods(class_id)
        return class_obj, methods

    def get_file_structure(self, file_id: int) -> Dict[str, Any]:
        """Get complete file structure (classes, functions, methods, imports).

        Args:
            file_id: File identifier

        Returns:
            Dictionary with keys: classes, functions, methods, imports

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        classes = self.get_file_classes(file_id)
        functions = self.get_file_functions(file_id)
        imports = self.get_file_imports(file_id)

        # Get methods for all classes
        all_methods = []
        for class_obj in classes:
            methods = self.get_class_methods(class_obj.id)
            all_methods.extend(methods)

        return {
            "classes": classes,
            "functions": functions,
            "methods": all_methods,
            "imports": imports,
        }
