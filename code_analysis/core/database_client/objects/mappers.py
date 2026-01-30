"""
Mapper functions for converting objects to/from database rows.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, List, Optional, Type, TypeVar

from .analysis import CodeDuplicate, Issue, Usage
from .ast_cst import ASTNode, CSTNode
from .base import BaseObject
from .class_function import Class, Function
from .method_import import Import, Method
from .vector_chunk import CodeChunk, VectorIndex
from .file import File
from .project import Project

T = TypeVar("T", bound=BaseObject)

# Mapping of table names to object classes
TABLE_TO_CLASS: Dict[str, Type[BaseObject]] = {
    "projects": Project,
    "files": File,
    "ast_trees": ASTNode,
    "cst_trees": CSTNode,
    "vector_index": VectorIndex,
    "code_chunks": CodeChunk,
    "classes": Class,
    "functions": Function,
    "methods": Method,
    "imports": Import,
    "issues": Issue,
    "usages": Usage,
    "code_duplicates": CodeDuplicate,
}


def object_to_db_row(obj: BaseObject) -> Dict[str, Any]:
    """Convert object to database row format.

    Args:
        obj: Object instance

    Returns:
        Dictionary suitable for database insertion/update
    """
    return obj.to_db_row()


def db_row_to_object(row: Dict[str, Any], object_class: Type[T]) -> T:
    """Convert database row to object.

    Args:
        row: Database row as dictionary
        object_class: Object class to create

    Returns:
        Object instance

    Raises:
        ValueError: If object creation fails
    """
    return object_class.from_db_row(row)


def db_rows_to_objects(rows: List[Dict[str, Any]], object_class: Type[T]) -> List[T]:
    """Convert list of database rows to objects.

    Args:
        rows: List of database rows as dictionaries
        object_class: Object class to create

    Returns:
        List of object instances
    """
    return [object_class.from_db_row(row) for row in rows]


def object_from_table(row: Dict[str, Any], table_name: str) -> Optional[BaseObject]:
    """Create object from database row using table name.

    Args:
        row: Database row as dictionary
        table_name: Name of database table

    Returns:
        Object instance or None if table not found

    Raises:
        ValueError: If object creation fails
    """
    object_class = TABLE_TO_CLASS.get(table_name)
    if object_class is None:
        return None
    return object_class.from_db_row(row)


def objects_from_table(rows: List[Dict[str, Any]], table_name: str) -> List[BaseObject]:
    """Create objects from database rows using table name.

    Args:
        rows: List of database rows as dictionaries
        table_name: Name of database table

    Returns:
        List of object instances (empty if table not found)
    """
    object_class = TABLE_TO_CLASS.get(table_name)
    if object_class is None:
        return []
    return [object_class.from_db_row(row) for row in rows]


def get_object_class_for_table(table_name: str) -> Optional[Type[BaseObject]]:
    """Get object class for table name.

    Args:
        table_name: Name of database table

    Returns:
        Object class or None if table not found
    """
    return TABLE_TO_CLASS.get(table_name)


def get_table_name_for_object(obj: BaseObject) -> Optional[str]:
    """Get table name for object instance.

    Args:
        obj: Object instance

    Returns:
        Table name or None if not found
    """
    obj_class = type(obj)
    for table_name, class_type in TABLE_TO_CLASS.items():
        if obj_class == class_type:
            return table_name
    return None
