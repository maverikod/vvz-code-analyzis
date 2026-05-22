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
            "universal_file_write is step 4 in the universal file edit workflow:\n"
            "  1. universal_file_open  — open a file, get session_id\n"
            "  2. universal_file_preview — obtain node_ref values\n"
            "  3. universal_file_edit  — apply operations to the in-memory draft\n"
            "  4. universal_file_write — preview diff, then commit to disk  (THIS COMMAND)\n"
            "  5. universal_file_close — release the session\n\n"
            "Write protocol by file type:\n\n"
            "JSON/YAML and plain text/markdown — explicit write_mode:\n"
            "  write_mode=preview (default): unified diff vs canonical file; no disk write.\n"
            "  write_mode=commit: backup original, atomic write from draft, delete lockfile.\n"
            "  Always call preview first, inspect the diff, then call commit.\n\n"
            "Python (.py) — legacy two-phase when write_mode is omitted:\n"
            "  First call: diff + lockfile, phase=preview.\n"
            "  Second call (lockfile matches PID+session): commit, phase=committed.\n"
            "  Explicit write_mode=preview or commit overrides the lockfile phase.\n\n"
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
                    "preview: diff only (tree-temp, text; also sidecar when sent explicitly). "
                    "commit: persist draft (tree-temp, text; sidecar). "
                    "Omitted on sidecar: two-phase PID lockfile (first preview, second commit)."
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
                    "write_mode": "Echoed write_mode when sent explicitly.",
                    "source_sha256_at_open": "SHA-256 of the file at open time (JSON/YAML commit).",
                    "structural_editing_restored": "True when a successful commit recovered node-based editing after line-based fallback (optional).",
                    "is_invalid": "False after structural editing is restored (optional).",
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
                "description": "Preview then commit a Markdown file (text)",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                    "write_mode": "preview",
                },
                "explanation": (
                    "Preview does not change the file on disk. "
                    "Call again with write_mode=commit to persist."
                ),
            },
            {
                "description": "Two-phase write for a Python file (sidecar, omit write_mode)",
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
            "For JSON/YAML and text: always call write_mode=preview first, then write_mode=commit.",
            "For Python without write_mode: first call is preview, second is commit.",
            "Repeated write_mode=preview must never commit; phase must match the action.",
            "After a successful commit, call format_code and lint_code on the file path.",
            "If the server restarts between preview and commit, the lockfile is stale; re-open the session.",
        ],
    }
