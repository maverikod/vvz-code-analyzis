"""
Module entities - database operations for code entities (classes, methods, functions, code_content).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def add_class(
    self,
    file_id: int,
    name: str,
    line: int,
    docstring: Optional[str],
    bases: List[str],
    end_line: Optional[int] = None,
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

    Returns:
        Class ID
    """
    bases_json = json.dumps(bases)
    self._execute(
        """
        INSERT OR REPLACE INTO classes (file_id, name, line, end_line, docstring, bases)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (file_id, name, line, end_line, docstring, bases_json),
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
    end_line: Optional[int] = None,
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

    Returns:
        Method ID
    """
    args_json = json.dumps(args)
    self._execute(
        """
        INSERT OR REPLACE INTO methods (class_id, name, line, end_line, args, docstring)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (class_id, name, line, end_line, args_json, docstring),
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
    end_line: Optional[int] = None,
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

    Returns:
        Function ID
    """
    args_json = json.dumps(args)
    self._execute(
        """
        INSERT OR REPLACE INTO functions (file_id, name, line, end_line, args, docstring)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (file_id, name, line, end_line, args_json, docstring),
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


def search_classes(
    self,
    name_pattern: Optional[str] = None,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search classes by name pattern.

    Args:
        name_pattern: Optional name pattern (SQL LIKE syntax, e.g., '%Manager')
        project_id: Optional project ID to filter by

    Returns:
        List of matching classes with file paths and metadata
    """
    # Build query with optional filters
    query = """
        SELECT 
            c.id,
            c.name,
            c.line,
            c.docstring,
            c.bases,
            f.path as file_path,
            f.project_id
        FROM classes c
        JOIN files f ON c.file_id = f.id
        WHERE 1=1
    """
    params = []
    
    if project_id:
        query += " AND f.project_id = ?"
        params.append(project_id)
    
    if name_pattern:
        query += " AND c.name LIKE ?"
        params.append(name_pattern)
    
    query += " ORDER BY c.name"
    
    rows = self._fetchall(query, tuple(params))
    
    # Convert to list of dicts and parse JSON fields
    results = []
    for row in rows:
        bases = []
        if row["bases"]:
            try:
                bases = json.loads(row["bases"])
            except (json.JSONDecodeError, TypeError):
                bases = []
        
        results.append({
            "id": row["id"],
            "name": row["name"],
            "line": row["line"],
            "docstring": row["docstring"],
            "bases": bases,
            "file_path": row["file_path"],
            "project_id": row["project_id"],
        })
    
    return results


def search_methods(
    self,
    name_pattern: Optional[str] = None,
    class_name: Optional[str] = None,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search methods, optionally filtered by class name.

    Args:
        name_pattern: Optional method name pattern (SQL LIKE syntax)
        class_name: Optional class name to filter by (exact match)
        project_id: Optional project ID to filter by

    Returns:
        List of matching methods with class and file information
    """
    # Build query with optional filters
    query = """
        SELECT 
            m.id,
            m.name,
            m.line,
            m.args,
            m.docstring,
            c.name as class_name,
            c.id as class_id,
            f.path as file_path,
            f.project_id
        FROM methods m
        JOIN classes c ON m.class_id = c.id
        JOIN files f ON c.file_id = f.id
        WHERE 1=1
    """
    params = []
    
    if project_id:
        query += " AND f.project_id = ?"
        params.append(project_id)
    
    if class_name:
        query += " AND c.name = ?"
        params.append(class_name)
    
    if name_pattern:
        query += " AND m.name LIKE ?"
        params.append(name_pattern)
    
    query += " ORDER BY c.name, m.line"
    
    rows = self._fetchall(query, tuple(params))
    
    # Convert to list of dicts and parse JSON fields
    results = []
    for row in rows:
        args = []
        if row["args"]:
            try:
                args = json.loads(row["args"])
            except (json.JSONDecodeError, TypeError):
                args = []
        
        results.append({
            "id": row["id"],
            "name": row["name"],
            "line": row["line"],
            "args": args,
            "docstring": row["docstring"],
            "class_name": row["class_name"],
            "class_id": row["class_id"],
            "file_path": row["file_path"],
            "project_id": row["project_id"],
        })
    
    return results


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
    self._commit()
    result = self._lastrowid()
    assert result is not None
    return result

