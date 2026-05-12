"""
Schema for project_file_lock_status.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict


def get_project_file_lock_status_schema() -> Dict[str, Any]:
    """Machine-readable schema for advisory lock status lookup."""
    return {
        "type": "object",
        "description": (
            "Return cooperative runtime advisory lock state for one project file "
            "from ``file_advisory_lock_leases`` (read-only). "
            "``file_path`` is relative to the **watched registered project** root "
            "(``list_projects`` → ``root_path`` under a watch_dir), not the "
            "code-analysis-server installation directory; absolute paths are rejected."
        ),
        "properties": {
            "project_id": {
                "type": "string",
                "description": "Project UUID (from list_projects).",
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Path relative to that project's ``root_path`` only (POSIX ``/``, "
                    "no leading ``/``, no ``..``). Must be an existing file inside the "
                    "registered project tree (watch_dir scope), not paths tied to the server app root."
                ),
            },
        },
        "required": ["project_id", "file_path"],
        "additionalProperties": False,
    }
