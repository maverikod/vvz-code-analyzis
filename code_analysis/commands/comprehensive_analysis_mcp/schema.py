"""
JSON schema for comprehensive_analysis command parameters.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict


def get_schema(cls: Any) -> Dict[str, Any]:
    """Build JSON schema for comprehensive_analysis (uses cls._get_base_schema_properties())."""
    base_props = cls._get_base_schema_properties()
    return {
        "type": "object",
        "description": (
            "Comprehensive code analysis combining multiple analysis types: "
            "placeholders, stubs, empty methods, imports not at top, long files, "
            "duplicates, missing docstrings, flake8 linting, mypy type checking. "
            "This is a long-running command and is executed via queue. "
            "Incremental: analyzes only files whose disk mtime is newer than or equal to "
            "the latest analysis timestamp in DB (with tolerance); older-than-DB files are skipped."
        ),
        "properties": {
            **base_props,
            "file_path": {
                "type": "string",
                "description": "Optional path to specific file to analyze",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum lines threshold for long files",
                "default": 400,
            },
            "check_placeholders": {
                "type": "boolean",
                "description": "Check for placeholders (TODO, FIXME, etc.)",
                "default": True,
            },
            "check_stubs": {
                "type": "boolean",
                "description": "Check for stub functions/methods",
                "default": True,
            },
            "check_empty_methods": {
                "type": "boolean",
                "description": "Check for empty methods",
                "default": True,
            },
            "check_imports": {
                "type": "boolean",
                "description": "Check for imports not at top of file",
                "default": True,
            },
            "check_long_files": {
                "type": "boolean",
                "description": "Check for long files",
                "default": True,
            },
            "check_duplicates": {
                "type": "boolean",
                "description": "Check for code duplicates",
                "default": True,
            },
            "check_flake8": {
                "type": "boolean",
                "description": "Check code with flake8 linter",
                "default": True,
            },
            "check_mypy": {
                "type": "boolean",
                "description": "Check code with mypy type checker",
                "default": True,
            },
            "check_black": {
                "type": "boolean",
                "description": (
                    "Check code formatting with black (--check; reports drift, "
                    "never rewrites). Opt-in; requires black in the server image."
                ),
                "default": False,
            },
            "check_isort": {
                "type": "boolean",
                "description": (
                    "Check import ordering with isort (--check-only). Opt-in; "
                    "requires isort in the server image."
                ),
                "default": False,
            },
            "check_bandit": {
                "type": "boolean",
                "description": (
                    "Scan for security issues with bandit. Opt-in; requires "
                    "bandit in the server image."
                ),
                "default": False,
            },
            "bandit_config_file": {
                "type": "string",
                "description": "Optional path to a bandit config file (-c).",
            },
            "check_docstrings": {
                "type": "boolean",
                "description": "Check for missing docstrings (files, classes, methods)",
                "default": True,
            },
            "duplicate_min_lines": {
                "type": "integer",
                "description": "Minimum lines for duplicate detection",
                "default": 5,
            },
            "duplicate_min_similarity": {
                "type": "number",
                "description": "Minimum similarity for duplicates",
                "default": 0.8,
            },
            "mypy_config_file": {
                "type": "string",
                "description": "Optional path to mypy config file",
            },
            "limit": {
                "type": "integer",
                "description": (
                    "Max number of files to analyze per run (e.g. 10–15). "
                    "None = all files. Use with offset for paging."
                ),
                "default": None,
            },
            "offset": {
                "type": "integer",
                "description": (
                    "Number of files to skip (for paging with limit). Default 0."
                ),
                "default": 0,
            },
            "check_missing_files_on_disk": {
                "type": "boolean",
                "description": (
                    "Project-level: detect active ``files`` rows missing on disk; "
                    "register ``missing_file_on_disk`` in ``issues``. Skipped while "
                    "file watcher holds the project lease."
                ),
                "default": True,
            },
            "check_circular_imports": {
                "type": "boolean",
                "description": (
                    "Project-level: detect circular import chains via indexed "
                    "``imports`` (SQL temp edges → tree → filter); register "
                    "``circular_import`` in ``issues``. Skipped while file watcher "
                    "holds the project lease."
                ),
                "default": True,
            },
            "max_import_chain_depth": {
                "type": "integer",
                "description": (
                    "Max import chain hops for circular-import SQL tree (default 10)."
                ),
                "default": 10,
                "minimum": 2,
                "maximum": 10,
            },
        },
        "required": ["project_id"],
        "additionalProperties": False,
    }
