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
            "  1. universal_file_open  — open (or create) a file; get session_id and format_group\n"
            "  2. universal_file_edit  — apply operations to the in-memory draft\n"
            "  3. universal_file_write — preview diff, then commit to disk\n"
            "  4. universal_file_close — release the session and reconcile artefacts\n\n"
            "format_group in the response determines how subsequent edit operations are shaped:\n"
            "  sidecar   (.py, .pyi, .pyw) — CST-based; node_ref is a stable UUID\n"
            "  tree-temp (.json, .yaml, .yml) — in-memory tree; node_ref is a JSON Pointer\n"
            "  text      (.md, .txt, .rst, .adoc, …) — line-based; node_ref is a zero-based index\n\n"
            "Parse-error fallback: when a JSON or YAML file cannot be parsed, the session\n"
            "opens in text mode instead of failing. The response includes fallback_reason\n"
            "and original_format_group so the caller knows the file has syntax errors.\n\n"
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
                    "For JSON/YAML, an empty object {} is written. "
                    "For text formats, an empty file is created."
                ),
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "initial_content": {
                "description": (
                    "Initial source code for new .py files (create=True only). "
                    "Must be valid Python; the CST tree is built from it immediately. "
                    "Ignored for non-Python formats."
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
                    "format_group": "One of: sidecar, tree-temp, text.",
                    "available_operations": "List of supported operation types: insert, delete, replace.",
                    "created": "True when create=True and the file did not exist (optional field).",
                    "fallback_reason": "PARSE_ERROR when JSON/YAML could not be parsed and text-mode fallback was used (optional).",
                    "original_format_group": "Format group that was originally resolved before fallback (optional).",
                },
                "example": {
                    "session_id": "4b4255c7-6a0c-4396-94c6-6f2bcf297912",
                    "format_group": "tree-temp",
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
                    "Returns session_id and format_group=tree-temp. "
                    "Use the session_id in subsequent universal_file_edit calls."
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
                    "create=True writes initial_content to disk, builds the CST tree, "
                    "and returns format_group=sidecar."
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
            "Check format_group in the response before calling universal_file_edit to use the correct operation shape.",
            "If fallback_reason=PARSE_ERROR is present, the file has syntax errors — fix them before committing.",
            "One session per file at a time — opening a second session on the same file returns PARSE_ERROR (locked).",
            "For Python files (sidecar): run universal_file_preview first to obtain stable node_ref UUIDs.",
        ],
    }
