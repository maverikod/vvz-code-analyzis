"""
Metadata for universal_file_open command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_universal_file_open_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_open.

    Args:
        cls: The command class (UniversalFileOpenCommand).

    Returns:
        Metadata dict with description, parameters, examples, errors.
    """
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Start an edit session for one project file.\n\n"
            "universal_file_open is step 1 in the universal file edit workflow:\n"
            "  1. universal_file_open  — open (or create) a file; get session_id\n"
            "  2. universal_file_preview — obtain node_ref values from the current draft\n"
            "  3. universal_file_edit  — apply operations to the in-memory draft\n"
            "  4. universal_file_write — preview diff, then commit to disk\n"
            "  5. universal_file_close — release the session and reconcile artefacts\n\n"
            "Edit operation shape is determined by universal_file_preview (node_id for "
            "Python, json_pointer for JSON/YAML, node_ref slug or line index for text).\n\n"
            "Parse-error fallback: when a structured file cannot be parsed, the session\n"
            "opens in line-based fallback instead of failing. The response includes "
            "is_invalid, fallback_reason, and warning.\n"
            "After fixing syntax and committing, structural (node-based) editing is "
            "restored automatically.\n\n"
            "Stale artefacts: on open, any existing write lockfile and draft file for the\n"
            "target are deleted (sidecar is preserved for Python files).\n\n"
            "Initial backup: when the file has no backup history, one is created automatically."
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "Project UUID. Use list_projects to discover valid values."
                ),
                "type": "string",
                "required": True,
                "examples": ["8772a086-688d-4198-a0c4-f03817cc0e6c"],
            },
            "file_path": {
                "description": (
                    "Project-relative path to the file to open. Literal path; no globs."
                ),
                "type": "string",
                "required": True,
                "examples": [
                    "code_analysis/commands/my_command.py",
                    "config/settings.yaml",
                ],
            },
            "create": {
                "description": (
                    "When True, create the file if it does not exist. "
                    "For .py files, initial_content is required. "
                    "For JSON/YAML, initial_content is written as raw text when "
                    "provided; otherwise an empty object {} is written. "
                    "For text formats, an empty file is created."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "initial_content": {
                "description": (
                    "Initial content for new files (create=True only). "
                    "For .py: required; CST tree is built after write. "
                    "For JSON/YAML: optional raw text written as-is (invalid syntax "
                    "opens in text mode with is_invalid). "
                    "Ignored for other formats."
                ),
                "type": "string",
                "required": False,
            },
        },
        "return_value": {
            "success": {
                "description": "Session opened; draft and lockfile created.",
                "data": {
                    "session_id": "UUID for subsequent edit/write/close calls.",
                    "available_operations": "List of supported operation types: insert, delete, replace.",
                    "created": "True when create=True and the file did not exist (optional field).",
                    "fallback_reason": "PARSE_ERROR when structured parse failed and line-based fallback was used (optional).",
                    "is_invalid": "True when the file has syntax errors and the session opened in line-based fallback (optional).",
                    "warning": "Human-readable explanation when is_invalid is True (optional).",
                },
                "example": {
                    "session_id": "4b4255c7-6a0c-4396-94c6-6f2bcf297912",
                    "available_operations": ["insert", "delete", "replace"],
                },
            },
            "error": {
                "description": "Session could not be opened.",
                "code": "Stable error code (see error_cases).",
                "message": "Human-readable description.",
            },
        },
        "usage_examples": [
            {
                "description": "Open an existing YAML config file for editing",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "config/settings.yaml",
                },
                "explanation": (
                    "Returns session_id. Run universal_file_preview next to obtain node_ref values."
                ),
            },
            {
                "description": "Create a new Python module",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "file_path": "code_analysis/commands/my_new_command.py",
                    "create": True,
                    "initial_content": "'''\nMy new command.\n'''\n\nfrom __future__ import annotations\n",
                },
                "explanation": (
                    "create=True writes initial_content to disk and builds the CST tree. "
                    "Run universal_file_preview before editing."
                ),
            },
        ],
        "error_cases": {
            "PARSE_ERROR": {
                "description": "File not found, locked by another session, or cleanup failed. "
                "For JSON/YAML parse errors, a text-mode fallback is used instead of this error.",
                "solution": "Check file_path exists, close any open sessions on the file, and retry.",
            },
            "UNKNOWN_FORMAT": {
                "description": "File extension not supported by any handler.",
                "solution": "Use a supported extension: .py, .json, .yaml, .yml, .md, .txt, .rst, .adoc.",
            },
        },
        "best_practices": [
            "Always call universal_file_close when done — sessions are not cleaned up on server restart.",
            "Always call universal_file_preview after open to obtain node_ref values for edits.",
            "If is_invalid is True, fix parse errors and commit before expecting node-based edits.",
            "One session per file at a time — opening a second session on the same file returns PARSE_ERROR (locked).",
        ],
    }
