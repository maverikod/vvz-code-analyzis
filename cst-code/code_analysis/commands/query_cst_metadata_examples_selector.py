"""
query_cst metadata: selector usage examples (stmt, function, import, complex).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List


def get_selector_examples() -> List[Dict[str, Any]]:
    """Return usage examples for stmt/function/import and complex selectors."""
    return [
        {
            "description": "Find all methods in a class",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/models.py",
                "selector": 'class[name="UserModel"] method',
            },
            "explanation": (
                "Finds all methods inside UserModel class. "
                "Uses descendant combinator (whitespace) to find methods at any depth."
            ),
        },
        {
            "description": "Find direct child methods only",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/models.py",
                "selector": 'class[name="UserModel"] > method',
            },
            "explanation": (
                "Finds only direct child methods of UserModel class (not nested methods). "
                "Uses child combinator (>) to find only direct children."
            ),
        },
        {
            "description": "Find all functions",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/utils.py",
                "selector": "function",
            },
            "explanation": (
                "Finds all top-level functions (not methods) in utils.py. "
                "Returns all function definitions at module level."
            ),
        },
        {
            "description": "Find functions by name prefix",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/utils.py",
                "selector": 'function[name^="get_"]',
            },
            "explanation": (
                "Finds all functions whose names start with 'get_' (e.g., get_user, get_data). "
                "Useful for finding getter functions."
            ),
        },
        {
            "description": "Find functions by name pattern",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/utils.py",
                "selector": 'function[name~="test"]',
            },
            "explanation": (
                "Finds all functions whose names contain 'test' (e.g., test_user, run_tests). "
                "Uses substring match operator (~=)."
            ),
        },
        {
            "description": "Find all if statements",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'stmt[type="If"]',
            },
            "explanation": (
                "Finds all if statements in main.py. "
                "Uses type attribute to match LibCST node type 'If'."
            ),
        },
        {
            "description": "Find all for loops",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'stmt[type="For"]',
            },
            "explanation": (
                "Finds all for loops in main.py. "
                "Uses type attribute to match LibCST node type 'For'."
            ),
        },
        {
            "description": "Find all try statements",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'stmt[type="Try"]',
            },
            "explanation": (
                "Finds all try-except blocks in main.py. "
                "Useful for analyzing error handling patterns."
            ),
        },
        {
            "description": "Find all with statements",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'stmt[type="With"]',
            },
            "explanation": (
                "Finds all with statements (context managers) in main.py. "
                "Useful for analyzing resource management."
            ),
        },
        {
            "description": "Find all import statements",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": "import",
            },
            "explanation": (
                "Finds all import statements (both 'import' and 'from ... import'). "
                "Uses 'import' kind alias."
            ),
        },
        {
            "description": "Find all assignments",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'smallstmt[type="Assign"]',
            },
            "explanation": (
                "Finds all assignment statements in main.py. "
                "Uses smallstmt kind and Assign type."
            ),
        },
        {
            "description": "Find all function calls",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'node[type="Call"]',
            },
            "explanation": (
                "Finds all function call expressions in main.py. "
                "Uses 'node' kind to match any node type, filters by Call type."
            ),
        },
        {
            "description": "Find nodes by line range",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": "node[start_line>=10][end_line<=20]",
            },
            "explanation": (
                "Finds all nodes that start at or after line 10 and end at or before line 20. "
                "Note: Line number predicates use string comparison, so '10' < '2' lexicographically. "
                "For numeric ranges, consider using multiple queries or filtering results."
            ),
        },
        {
            "description": "Find all statements (any type)",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": "stmt",
            },
            "explanation": (
                "Finds all statement nodes (if, for, while, try, with, etc.) in main.py. "
                "Uses 'stmt' kind alias."
            ),
        },
        {
            "description": "Find all small statements",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": "smallstmt",
            },
            "explanation": (
                "Finds all small statement nodes (return, break, continue, pass, assign, etc.) in main.py. "
                "Uses 'smallstmt' kind alias."
            ),
        },
        {
            "description": "Find any node type (wildcard)",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": "*",
            },
            "explanation": (
                "Finds all nodes in main.py. "
                "Uses wildcard (*) to match any node type. "
                "Warning: This can return a very large number of results."
            ),
        },
        {
            "description": "Complex query: return in if inside function",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'function[name="process"] stmt[type="If"] smallstmt[type="Return"]',
            },
            "explanation": (
                "Finds return statements inside if statements inside process function. "
                "Uses multiple descendant combinators to navigate the tree structure."
            ),
        },
        {
            "description": "Complex query: method calls in specific class",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'class[name="DataProcessor"] node[type="Call"]',
            },
            "explanation": (
                "Finds all function calls inside DataProcessor class. "
                "Uses descendant combinator to find calls at any depth."
            ),
        },
        {
            "description": "Find nodes excluding specific type",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'stmt[type!="Pass"]',
            },
            "explanation": (
                "Finds all statements except Pass statements. "
                "Uses not equal operator (!=) to exclude specific type."
            ),
        },
    ]
