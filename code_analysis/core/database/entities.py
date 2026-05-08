"""
Module entities - database operations for code entities (classes, methods, functions, code_content).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
import uuid
from typing import List, Optional

logger = logging.getLogger(__name__)


def _validate_cst_node_id_uuid4(cst_node_id: str, entity_kind: str) -> None:
    """
    Validate that cst_node_id is non-empty and valid UUID4. Fail-fast with explicit error.

    Args:
        cst_node_id: Value to validate.
        entity_kind: Label for error message (e.g. 'class', 'method', 'function').

    Raises:
        ValueError: If cst_node_id is missing, empty, or not a valid UUID4.
    """
    if not cst_node_id or not isinstance(cst_node_id, str):
        raise ValueError(
            f"cst_node_id for {entity_kind} is required and must be a non-empty string; got {type(cst_node_id).__name__!r}"
        )
    s = cst_node_id.strip()
    if not s:
        raise ValueError(
            f"cst_node_id for {entity_kind} must be non-empty (got whitespace-only)"
        )
    try:
        u = uuid.UUID(s, version=4)
        if str(u) != s:
            raise ValueError(
                f"cst_node_id for {entity_kind} must be canonical UUID4 string; got {cst_node_id!r}"
            )
    except (ValueError, TypeError) as e:
        if isinstance(e, ValueError) and "version" in str(e).lower():
            raise ValueError(
                f"cst_node_id for {entity_kind} must be valid UUID4; got {cst_node_id!r}"
            ) from e
        raise ValueError(
            f"cst_node_id for {entity_kind} must be valid UUID4; got {cst_node_id!r}"
        ) from e


def add_class(
    self,
    file_id: int,
    name: str,
    line: int,
    docstring: Optional[str],
    bases: List[str],
    end_line: Optional[int] = None,
    cst_node_id: Optional[str] = None,
) -> int:
    """
    Add class to database.

    Args:
        file_id: File ID
        name: Class name
        line: Line number
        docstring: Class docstring
        bases: List of base class names
        end_line: Optional end line (for entity cross-ref resolution)
        cst_node_id: CST node ID (UUID4); required for entity writes.

    Returns:
        Class ID

    Raises:
        ValueError: If cst_node_id is missing, empty, or not valid UUID4.
    """
    _validate_cst_node_id_uuid4(cst_node_id or "", "class")
    bases_json = json.dumps(bases)
    self._execute(
        """
        INSERT OR REPLACE INTO classes (file_id, name, line, end_line, docstring, bases, cst_node_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (file_id, name, line, end_line, docstring, bases_json, cst_node_id),
    )
    if not self._in_transaction():
        self._commit()
    result = self._lastrowid()
    assert result is not None
    return result


def add_method(
    self,
    class_id: int,
    name: str,
    line: int,
    args: List[str],
    docstring: Optional[str],
    complexity: Optional[int] = None,
    end_line: Optional[int] = None,
    cst_node_id: Optional[str] = None,
) -> int:
    """
    Add method to database.

    Args:
        class_id: Class ID
        name: Method name
        line: Line number
        args: List of argument names
        docstring: Method docstring
        complexity: Cyclomatic complexity (optional)
        end_line: Optional end line (for entity cross-ref resolution)
        cst_node_id: CST node ID (UUID4); required for entity writes.

    Returns:
        Method ID

    Raises:
        ValueError: If cst_node_id is missing, empty, or not valid UUID4.
    """
    _validate_cst_node_id_uuid4(cst_node_id or "", "method")
    args_json = json.dumps(args)
    self._execute(
        """
        INSERT OR REPLACE INTO methods (class_id, name, line, end_line, args, docstring, cst_node_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (class_id, name, line, end_line, args_json, docstring, cst_node_id),
    )
    if not self._in_transaction():
        self._commit()
    result = self._lastrowid()
    assert result is not None
    return result


def add_function(
    self,
    file_id: int,
    name: str,
    line: int,
    args: List[str],
    docstring: Optional[str],
    complexity: Optional[int] = None,
    end_line: Optional[int] = None,
    cst_node_id: Optional[str] = None,
) -> int:
    """
    Add function to database.

    Args:
        file_id: File ID
        name: Function name
        line: Line number
        args: List of argument names
        docstring: Function docstring
        complexity: Cyclomatic complexity (optional)
        end_line: Optional end line (for entity cross-ref resolution)
        cst_node_id: CST node ID (UUID4); required for entity writes.

    Returns:
        Function ID

    Raises:
        ValueError: If cst_node_id is missing, empty, or not valid UUID4.
    """
    _validate_cst_node_id_uuid4(cst_node_id or "", "function")
    args_json = json.dumps(args)
    self._execute(
        """
        INSERT OR REPLACE INTO functions (file_id, name, line, end_line, args, docstring, cst_node_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (file_id, name, line, end_line, args_json, docstring, cst_node_id),
    )
    if not self._in_transaction():
        self._commit()
    result = self._lastrowid()
    assert result is not None
    return result


def add_import(
    self,
    file_id: int,
    name: str,
    module: Optional[str],
    import_type: str,
    line: int,
) -> int:
    """
    Add import to database.

    Args:
        file_id: File ID
        name: Import name
        module: Module name (for import_from)
        import_type: Type of import ('import' or 'import_from')
        line: Line number

    Returns:
        Import ID
    """
    self._execute(
        """
        INSERT INTO imports (file_id, name, module, import_type, line)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, name, module, import_type, line),
    )
    if not self._in_transaction():
        self._commit()
    result = self._lastrowid()
    assert result is not None
    return result
def add_code_content(
    self,
    file_id: int,
    entity_type: str,
    entity_name: str,
    content: str,
    docstring: Optional[str],
    entity_id: Optional[int] = None,
) -> int:
    """
    Add code content to database and FTS index.

    On PostgreSQL, code_content_fts (FTS5 virtual table) does not exist;
    fulltext search runs via to_tsvector directly on code_content.
    On SQLite, also inserts into code_content_fts for FTS5 MATCH queries.

    Args:
        file_id: File ID
        entity_type: Type of entity ('file', 'class', 'function', 'method')
        entity_name: Name of entity
        content: Code content (source code of the entity)
        docstring: Docstring
        entity_id: Entity ID (for classes, functions, methods)

    Returns:
        Content ID
    """
    from ..sql_portable import database_has_sqlite_code_content_fts

    # Insert into code_content
    self._execute(
        """
        INSERT INTO code_content (file_id, entity_type, entity_id, entity_name, content, docstring)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (file_id, entity_type, entity_id, entity_name, content, docstring),
    )
    if not self._in_transaction():
        self._commit()
    result = self._lastrowid()
    assert result is not None

    # Insert into FTS index only on SQLite (FTS5 virtual table does not exist on PostgreSQL).
    if database_has_sqlite_code_content_fts(self):
        try:
            self._execute(
                """
                INSERT INTO code_content_fts (rowid, entity_type, entity_name, content, docstring)
                VALUES (?, ?, ?, ?, ?)
                """,
                (result, entity_type, entity_name, content, docstring or ""),
            )
            if not self._in_transaction():
                self._commit()
        except Exception as e:
            logger.warning(f"Failed to add content to FTS index: {e}", exc_info=True)
            # Continue anyway - FTS is optional

    return result


def add_usage(
    self,
    file_id: int,
    line: int,
    usage_type: str,
    target_type: str,
    target_name: str,
    target_class: Optional[str] = None,
    context: Optional[str] = None,
) -> int:
    """
    Add usage record to database.

    Args:
        file_id: File ID where usage occurs
        line: Line number where usage occurs
        usage_type: Type of usage ('call', 'instantiation', 'attribute', 'inheritance')
        target_type: Type of target ('class', 'function', 'method', 'property')
        target_name: Name of target entity
        target_class: Optional class name (for methods/properties)
        context: Optional context information

    Returns:
        Usage ID
    """
    self._execute(
        """
        INSERT INTO usages (file_id, line, usage_type, target_type, target_name, target_class, context)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (file_id, line, usage_type, target_type, target_name, target_class, context),
    )
    if not self._in_transaction():
        self._commit()
    result = self._lastrowid()
    assert result is not None
    return result
