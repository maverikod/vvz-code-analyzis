"""
query_cst metadata: find/replace usage examples (class, return, method, range).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List


def get_find_examples() -> List[Dict[str, Any]]:
    """Return usage examples for find/replace and class/return/method selectors."""
    return [
        {
            "description": "Find class by exact name",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'class[name="MyClass"]',
            },
            "explanation": (
                "Finds all classes named exactly 'MyClass' in main.py. "
                "Returns node_id that can be used with cst_modify_tree."
            ),
        },
        {
            "description": "Find class by name prefix",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
            "description": "Replace multiple matches with different code (replacements array)",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "selector": 'smallstmt[type="Return"]',
                "replacements": [
                    {"match_index": 0, "replace_with": "return None"},
                    {"match_index": 1, "code_lines": ["return 0"]},
                ],
            },
            "explanation": (
                "Replaces first return with 'return None', second with 'return 0'. "
                "Each entry in replacements has match_index (0-based) and replace_with or code_lines."
            ),
        },
        {
            "description": "Range-based replace (start_line and end_line)",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "src/main.py",
                "start_line": 10,
                "end_line": 15,
                "replace_with": "# replaced block",
            },
            "explanation": (
                "Replaces the statement(s) covering lines 10-15 (1-based) with new code. "
                "Selector is optional when both start_line and end_line are set."
            ),
        },
        {
            "description": "Find all return statements with code",
            "command": {
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
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
    ]
