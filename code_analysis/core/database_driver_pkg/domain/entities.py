"""
Class / method / issue entity operations, ported driver-direct (stage 2 layer
collapse, Part 1).

Free-function port of the live subset of
``code_analysis.core.database_client.client_api_classes_functions``'s
``_ClientAPIClassesFunctionsMixin`` (``search_classes``),
``client_api_methods_imports``'s ``_ClientAPIMethodsImportsMixin``
(``get_class_methods``, ``search_methods``), and ``client_api_issues_usages``'s
``_ClientAPIIssuesUsagesMixin`` (``create_issue``). Each function takes
``driver: Any`` (duck-typed against ``execute``/``select``/``insert`` - see
scratchpad/stage2-parity-spike.md) instead of ``self``.

NOT ported (confirmed zero production callers, stage 2 call map §1.2's 44
zero-caller list, re-verified with a fresh grep during this port):
``create_class``, ``create_method``, ``create_usage``, ``get_class``,
``get_class_with_methods``, ``get_method``, ``get_usage``, ``get_import``,
``get_issue``, ``search_functions``, ``search_imports``, ``search_usages``, and
the rest of ``client_api_classes_functions.py``/``client_api_methods_imports.py``/
``client_api_issues_usages.py``'s type-object CRUD (``add_import`` for this file's
purposes lives in ``domain/files.py`` - it is defined on ``client_api_files.py``,
not here, despite the similar name in the neighboring mixin files).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from code_analysis.core.database_client.objects.analysis import Issue
from code_analysis.core.database_client.objects.class_function import Class
from code_analysis.core.database_client.objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)
from code_analysis.core.database_client.objects.method_import import Method


def search_classes(
    driver: Any, project_id: Optional[str] = None, name: Optional[str] = None
) -> List[Class]:
    """Search classes by criteria.

    Exact port of ``_ClientAPIClassesFunctionsMixin.search_classes``.
    """
    if project_id:
        sql = """
            SELECT c.* FROM classes c
            JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ?
        """
        params: List[Any] = [project_id]
        if name:
            sql += " AND c.name LIKE ?"
            params.append(f"%{name}%")
        sql += " ORDER BY c.line"
        result = driver.execute(sql, tuple(params))
        rows = result.get("data", [])
    else:
        if name:
            sql = "SELECT * FROM classes WHERE name LIKE ? ORDER BY line"
            result = driver.execute(sql, (f"%{name}%",))
            rows = result.get("data", [])
        else:
            rows = driver.select("classes", order_by=["line"])

    return db_rows_to_objects(rows, Class)


def get_class_methods(driver: Any, class_id: int) -> List[Method]:
    """Get all methods for a class.

    Exact port of ``_ClientAPIMethodsImportsMixin.get_class_methods``.
    """
    rows = driver.select("methods", where={"class_id": class_id}, order_by=["line"])
    return db_rows_to_objects(rows, Method)


def search_methods(
    driver: Any,
    class_id: Optional[int] = None,
    name: Optional[str] = None,
    is_abstract: Optional[bool] = None,
) -> List[Method]:
    """Search methods by criteria.

    Exact port of ``_ClientAPIMethodsImportsMixin.search_methods``.
    """
    if name:
        sql = "SELECT * FROM methods WHERE 1=1"
        params: List[Any] = []
        if class_id:
            sql += " AND class_id = ?"
            params.append(class_id)
        sql += " AND name LIKE ?"
        params.append(f"%{name}%")
        if is_abstract is not None:
            sql += " AND is_abstract = ?"
            params.append(bool(is_abstract))
        sql += " ORDER BY line"
        result = driver.execute(sql, tuple(params))
        rows = result.get("data", [])
    else:
        where: Dict[str, Any] = {}
        if class_id:
            where["class_id"] = class_id
        if is_abstract is not None:
            where["is_abstract"] = bool(is_abstract)
        rows = driver.select("methods", where=where, order_by=["line"])

    return db_rows_to_objects(rows, Method)


def create_issue(driver: Any, issue: Issue) -> Issue:
    """Create new issue in database.

    Exact port of ``_ClientAPIIssuesUsagesMixin.create_issue``.
    """
    table_name = get_table_name_for_object(issue)
    if table_name is None:
        raise ValueError("Unknown table for Issue object")

    data = object_to_db_row(issue)
    row_id = driver.insert(table_name, data)
    if row_id is None:
        raise ValueError("Failed to create issue: insert returned no row id")

    rows = driver.select(table_name, where={"id": row_id})
    if not rows:
        raise ValueError("Failed to create issue")

    return db_row_to_object(rows[0], Issue)
