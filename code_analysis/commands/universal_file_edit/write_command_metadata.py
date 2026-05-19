"""
Metadata for universal_file_write command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_universal_file_write_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_write.

    Args:
        cls: The command class (UniversalFileWriteCommand).

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
            "Persist draft changes from an edit session to disk.\n\n"
            "universal_file_write is step 3 in the universal file edit workflow:\n"
            "  1. universal_file_open  — open a file, get session_id and format_group\n"
            "  2. universal_file_edit  — apply operations to the in-memory draft\n"
            "  3. universal_file_write — preview diff, then commit to disk  (THIS COMMAND)\n"
            "  4. universal_file_close — release the session\n\n"
            "Two protocols depending on format_group:\n\n"
            "tree-temp (.json, .yaml, .yml) — explicit write_mode:\n"
            "  write_mode=preview (default): compute and return the diff; no disk write, no lockfile.\n"
            "  write_mode=commit: backup original, write atomically, update indexes.\n"
            "  Always call preview first, inspect the diff, then call commit.\n\n"
            "sidecar (.py) and text — two-phase PID lockfile protocol:\n"
            "  First call: compute diff, write lockfile with current server PID. Returns phase=preview.\n"
            "  Second call (same session, lockfile valid): backup, atomic write, delete lockfile. Returns phase=committed.\n"
            "  The write_mode parameter is ignored for sidecar/text.\n\n"
            "A backup of the original file is always created before the commit write."
        ),
        "parameters": {
            "project_id": {
                "description": "Project UUID. Use list_projects to discover valid values.",
                "type": "string",
                "required": True,
                "examples": ["8772a086-688d-4198-a0c4-f03817cc0e6c"],
            },
            "session_id": {
                "description": (
                    "Active session UUID returned by universal_file_open. "
                    "Sessions are invalidated on server restart."
                ),
                "type": "string",
                "required": True,
            },
            "write_mode": {
                "description": (
                    "Tree-temp only: preview returns a diff without writing; "
                    "commit persists the file. Ignored for sidecar/text (two-phase PID protocol)."
                ),
                "type": "string",
                "required": False,
                "default": "preview",
                "enum": ["preview", "commit"],
            },
        },
        "return_value": {
            "success": {
                "description": "Write phase completed without errors.",
                "data": {
                    "phase": "preview or committed.",
                    "diff": "Unified diff string showing changes (present on both phases).",
                    "write_mode": "Echoed write_mode (tree-temp only).",
                    "source_sha256_at_open": "SHA-256 of the file at open time (tree-temp commit).",
                },
                "example": {
                    "phase": "preview",
                    "diff": "--- a/config.yaml\n+++ b/config.yaml\n...",
                },
            },
            "error": {
                "description": "Write failed; no disk changes were made.",
                "code": "Stable error code (see error_cases).",
                "message": "Human-readable description.",
            },
        },
        "usage_examples": [
            {
                "description": "Preview then commit a YAML file (tree-temp)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "write_mode": "preview",
                },
                "explanation": (
                    "First call with write_mode=preview returns the diff. "
                    "Inspect it, then call again with write_mode=commit to persist."
                ),
            },
            {
                "description": "Two-phase write for a Python file (sidecar)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                },
                "explanation": (
                    "First call returns phase=preview and creates the lockfile. "
                    "Second call with the same session returns phase=committed and writes the file."
                ),
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": {
                "description": "session_id is not registered; server may have restarted.",
                "solution": "Re-open the file with universal_file_open.",
            },
            "WRITE_FAILED": {
                "description": "Backup or atomic write failed.",
                "solution": "Check disk space and permissions under the project root.",
            },
            "SOURCE_CHANGED": {
                "description": "File on disk changed since the session was opened (tree-temp).",
                "solution": "Close the session, re-open, re-apply edits, and retry.",
            },
        },
        "best_practices": [
            "For tree-temp: always call write_mode=preview first and inspect the diff before committing.",
            "For sidecar/text: the first call is automatically preview; the second is commit — do not skip the first.",
            "After a successful commit, call format_code and lint_code on the file path.",
            "If the server restarts between preview and commit, the lockfile is stale; re-open the session.",
        ],
    }
