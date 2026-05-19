"""
Metadata for universal_file_close command (AI/docs).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_universal_file_close_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Return command metadata dict for universal_file_close.

    Args:
        cls: The command class (UniversalFileCloseCommand).

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
            "End an edit session and clean up all session artefacts.\n\n"
            "universal_file_close is step 4 (final) in the universal file edit workflow:\n"
            "  1. universal_file_open  — open a file, get session_id and format_group\n"
            "  2. universal_file_edit  — apply operations to the in-memory draft\n"
            "  3. universal_file_write — preview diff, then commit to disk\n"
            "  4. universal_file_close — release the session  (THIS COMMAND)\n\n"
            "What close does per format_group:\n\n"
            "sidecar (.py):\n"
            "  Verifies the sidecar SHA-256 against the source file. If they match,\n"
            "  the sidecar is left intact for the next session. If they differ (e.g.\n"
            "  the file was modified externally), the sidecar is rebuilt from source.\n"
            "  The write lockfile is deleted. draft_rebuilt=true is returned when the\n"
            "  sidecar had to be rebuilt.\n\n"
            "tree-temp (.json, .yaml, .yml):\n"
            "  Deletes the draft file and frees the in-memory tree. The write lockfile\n"
            "  is deleted. If the draft differs from disk (uncommitted edits), the draft\n"
            "  is rebuilt from the on-disk source — uncommitted changes are discarded.\n\n"
            "text (.md, .txt, .rst, .adoc, …):\n"
            "  Deletes the draft file and write lockfile. Uncommitted edits are discarded.\n\n"
            "Uncommitted edits (universal_file_edit without universal_file_write commit)\n"
            "are silently discarded on close. Always commit before closing if changes matter."
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
        },
        "return_value": {
            "success": {
                "description": "Session released and artefacts cleaned up.",
                "data": {
                    "success": "Always True on success.",
                    "draft_rebuilt": "True when the sidecar or draft was rebuilt from source (sidecar/tree-temp only).",
                },
                "example": {"success": True, "draft_rebuilt": False},
            },
            "error": {
                "description": "Session could not be closed.",
                "code": "Stable error code (see error_cases).",
                "message": "Human-readable description.",
            },
        },
        "usage_examples": [
            {
                "description": "Full lifecycle: open → edit → write → close",
                "command": {
                    "project_id": "8772a086-688d-4198-a0c4-f03817cc0e6c",
                    "session_id": "<from universal_file_open>",
                },
                "explanation": (
                    "After universal_file_write (commit), call close to release the session "
                    "and delete the draft file. Always close even if write failed."
                ),
            },
        ],
        "error_cases": {
            "SESSION_NOT_FOUND": {
                "description": "session_id is not registered; server may have restarted.",
                "solution": "Nothing to close — the session was already lost on restart.",
            },
        },
        "best_practices": [
            "Always close sessions after write to release the lockfile and free memory.",
            "Call close even when write failed — it cleans up partial artefacts.",
            "Unclosed sessions are lost on server restart but lockfiles may remain on disk; re-opening the file clears them.",
            "Do not call close before committing if you still need to inspect the diff.",
        ],
    }
