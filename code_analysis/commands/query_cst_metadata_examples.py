"""
query_cst metadata: usage_examples.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List


def get_usage_examples() -> List[Dict[str, Any]]:
    """Return the usage_examples list for query_cst metadata."""
    return [
        {
            "description": "Find class by exact name",
            "command": {
                "root_dir": "/home/user/projects/my_project",
                "file_path": "src/main.py",
                "selector": 'class[name="MyClass"]',
            },
            "explanation": (
                "Finds all classes named exactly 'MyClass' in main.py. "
                "Returns node_id that can be used with compose_cst_module."
            ),
        },
        {
            "description": "Find class by name prefix",
            "command": {
                "root_dir": "/home/user/projects/my_project",
                "file_path": "src/models.py",
                "selector": 'class[name^="Base"]',
            },
            "explanation": (
                "Finds all classes whose names start with 'Base' (e.g., BaseModel, BaseView). "
                "Uses prefix match operator (^=)."
            ),
        },
        {
            "description": "Find class by name suffix",
            "command": {
                "root_dir": "/home/user/projects/my_project",
                "file_path": "src/handlers.py",
                "selector": 'class[name$="Handler"]',
            },
            "explanation": (
                "Finds all classes whose names end with 'Handler' (e.g., RequestHandler, EventHandler). "
                "Uses suffix match operator ($=)."
            ),
        },
        {
            "description": "Find class by name substring",
            "command": {
                "root_dir": "/home/user/projects/my_project",
                "file_path": "src/services.py",
                "selector": 'class[name~="Service"]',
            },
            "explanation": (
                "Finds all classes whose names contain 'Service' (e.g., UserService, PaymentService). "
                "Uses substring match operator (~=)."
            ),
        },
        {
            "description": "Find all return statements",
            "command": {
                "root_dir": "/home/user/projects/my_project",
                "file_path": "src/utils.py",
                "selector": 'smallstmt[type="Return"]',
            },
            "explanation": (
                "Finds all return statements in utils.py. "
                "Useful for analyzing control flow and finding early returns."
            ),
        },
        {
            "description": "Replace first match (find + replace in one call)",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/utils.py",
                "selector": 'function[name="old_helper"] smallstmt[type="Return"]:first',
                "replace_with": "return default",
            },
            "explanation": (
                "Replaces the first return in old_helper with 'return default'. "
                "File is backed up and saved; response has replaced count and backup_uuid."
            ),
        },
        {
            "description": "Replace all matches with same code",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'smallstmt[type="Pass"]',
                "code_lines": ["raise NotImplementedError()"],
                "replace_all": True,
            },
            "explanation": (
                "Replaces every 'pass' statement with 'raise NotImplementedError()'. "
                "Use code_lines for multi-line replacement."
            ),
        },
        {
            "description": "Find all return statements with code",
            "command": {
                "root_dir": "/home/user/projects/my_project",
                "file_path": "src/utils.py",
                "selector": 'smallstmt[type="Return"]',
                "include_code": True,
            },
            "explanation": (
                "Finds all return statements and includes their code snippets. "
                "Useful for analyzing what values are being returned."
            ),
        },
        {
            "description": "Find first return in specific function",
            "command": {
                "root_dir": "/home/user/projects/my_project",
                "file_path": "src/main.py",
                "selector": 'function[name="process_data"] smallstmt[type="Return"]:first',
                "include_code": True,
            },
            "explanation": (
                "Finds the first return statement in process_data function. "
                "Uses descendant combinator (whitespace) and :first pseudo. "
                "Includes code snippet in response."
            ),
        },
        {
            "description": "Find last return in function",
            "command": {
                "root_dir": "/home/user/projects/my_project",
                "file_path": "src/main.py",
                "selector": 'function[name="process_data"] smallstmt[type="Return"]:last',
            },
            "explanation": (
                "Finds the last return statement in process_data function. "
                "Uses :last pseudo selector."
            ),
        },
        {
            "description": "Find nth return statement (0-based)",
            "command": {
                "root_dir": "/home/user/projects/my_project",
                "file_path": "src/main.py",
                "selector": 'function[name="process_data"] smallstmt[type="Return"]:nth(1)',
            },
            "explanation": (
                "Finds the second return statement (index 1, 0-based) in process_data function. "
                "Uses :nth(N) pseudo selector."
            ),
        },
        {
            "description": "Find method by qualified name",
            "command": {
                "root_dir": ".",
                "file_path": "code_analysis/core/backup_manager.py",
                "selector": 'method[qualname="BackupManager.restore_file"]',
                "include_code": True,
            },
            "explanation": (
                "Finds restore_file method in BackupManager class using qualified name. "
                "Qualified name format: ClassName.method_name. "
                "Includes code snippet in response."
            ),
        },
        {
            "description": "Find all methods in a class",
            "command": {
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
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
                "root_dir": "/home/user/projects/my_project",
                "file_path": "src/main.py",
                "selector": 'stmt[type!="Pass"]',
            },
            "explanation": (
                "Finds all statements except Pass statements. "
                "Uses not equal operator (!=) to exclude specific type."
            ),
        },
    ]
