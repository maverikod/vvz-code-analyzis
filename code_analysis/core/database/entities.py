"""
Module entities - database operations for code entities (classes, methods, functions, code_content).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def add_class(
    self,
    file_id: int,
    name: str,
    line: int,
    docstring: Optional[str],
    bases: List[str],
) -> int:
    """
    Add class to database.

    Args:
        file_id: File ID
        name: Class name
        line: Line number
        docstring: Class docstring
        bases: List of base class names

    Returns:
        Class ID
    """
    bases_json = json.dumps(bases)
    self._execute(
        """
        INSERT OR REPLACE INTO classes (file_id, name, line, docstring, bases)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, name, line, docstring, bases_json),
    )
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

    Returns:
        Method ID
    """
    args_json = json.dumps(args)
    self._execute(
        """
        INSERT OR REPLACE INTO methods (class_id, name, line, args, docstring)
        VALUES (?, ?, ?, ?, ?)
        """,
        (class_id, name, line, args_json, docstring),
    )
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

    Returns:
        Function ID
    """
    args_json = json.dumps(args)
    self._execute(
        """
        INSERT OR REPLACE INTO functions (file_id, name, line, args, docstring)
        VALUES (?, ?, ?, ?, ?)
        """,
        (file_id, name, line, args_json, docstring),
    )
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

    Args:
        file_id: File ID
        entity_type: Type of entity ('file', 'class', 'function', 'method')
        entity_name: Name of entity
        content: Code content
        docstring: Docstring
        entity_id: Entity ID (for classes, functions, methods)

    Returns:
        Content ID
    """
    # Insert into code_content
    self._execute(
        """
        INSERT INTO code_content (file_id, entity_type, entity_id, entity_name, content, docstring)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (file_id, entity_type, entity_id, entity_name, content, docstring),
    )
    self._commit()
    result = self._lastrowid()
    assert result is not None
    
    # Insert into FTS index
    try:
        self._execute(
            """
            INSERT INTO code_content_fts (rowid, entity_type, entity_name, content, docstring)
            VALUES (?, ?, ?, ?, ?)
            """,
            (result, entity_type, entity_name, content, docstring or ""),
        )
        self._commit()
    except Exception as e:
        logger.warning(f"Failed to add content to FTS index: {e}", exc_info=True)
        # Continue anyway - FTS is optional
    
    return result

