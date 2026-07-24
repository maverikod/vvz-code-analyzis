"""
MCP command: emergency_unlock_project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

from ._shared import (
    Any,
    BaseMCPCommand,
    Dict,
    ErrorResult,
    SuccessResult,
)


class EmergencyUnlockProjectMCPCommand(BaseMCPCommand):
    """
    Report on, or force-clear, the whole-project exclusive lock for a project.

    This is the ONE command exempt from ``BaseMCPCommand.run()``'s
    project-exclusive-lock gate (``_PROJECT_LOCK_GATE_EXEMPT_COMMANDS``): its
    whole purpose is to act on a project that IS locked. ``force=false`` (the
    safe default posture) only REPORTS the current lock state plus a
    best-effort disk/DB mismatch report; nothing is cleared unless
    ``force=true`` is passed explicitly, together with a ``reason`` that is
    folded into the structured audit log line.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue (False - single lookup/delete).
    """

    name = "emergency_unlock_project"
    version = "1.0.0"
    descr = (
        "Report on (force=false) or force-clear (force=true) the whole-project "
        "exclusive lock for a project. Exempt from the project-lock gate."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["EmergencyUnlockProjectMCPCommand"],
    ) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": (
                "Report on, or force-clear, the whole-project exclusive lock "
                "for a project (core/project_exclusive_lock.py)."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID to inspect/unlock.",
                },
                "force": {
                    "type": "boolean",
                    "description": (
                        "Must be true to actually clear the lock; without it the "
                        "command only REPORTS the lock state and any disk/DB "
                        "mismatch, it does not clear anything."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "Why you are force-clearing this lock - becomes part of "
                        "the audit log line."
                    ),
                },
            },
            "required": ["project_id", "force", "reason"],
            "additionalProperties": False,
        }

    async def execute(
        self: "EmergencyUnlockProjectMCPCommand",
        project_id: str,
        force: bool,
        reason: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Report on, or force-clear, the whole-project exclusive lock.

        Args:
            self: Command instance.
            project_id: Project UUID to inspect/unlock.
            force: Must be True to actually clear the lock.
            reason: Human-readable reason, folded into the audit log line.
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult describing the lock state (force=false) or the
            forced-clear audit record (force=true); ErrorResult on failure.
        """
        from ...core.project_exclusive_lock import (
            emergency_unlock_project_lock,
            get_project_exclusive_lock,
        )
        from ...core.project_root_path import resolve_project_root_absolute_str

        db = self._open_database_from_config()
        try:
            lock = get_project_exclusive_lock(db, project_id)

            # Mismatch detection: best-effort report of what the DB currently
            # thinks the root path is, and whether that path exists on disk.
            # require_exists=False - the dir may legitimately be missing if a
            # rename's Step 2 (disk rename) succeeded but Step 3 (DB update)
            # failed, or vice versa.
            rows = db.select("projects", where={"id": project_id})
            row = dict(rows[0]) if rows else {}
            resolved_root: str = ""
            try:
                resolved_root = resolve_project_root_absolute_str(
                    project_id=project_id,
                    root_path_stored=str(row.get("root_path") or ""),
                    watch_dir_id=(
                        str(row["watch_dir_id"])
                        if row.get("watch_dir_id") is not None
                        else None
                    ),
                    project_name=str(row.get("name") or "").strip() or None,
                    database=db,
                    require_exists=False,
                ).strip()
            except Exception:
                resolved_root = ""
            mismatch: Dict[str, Any] = {
                "db_root_path": resolved_root or None,
                "db_root_exists_on_disk": (
                    Path(resolved_root).is_dir() if resolved_root else None
                ),
                "stored_name": row.get("name"),
            }

            if not force:
                return SuccessResult(
                    data={
                        "project_id": project_id,
                        "locked": lock is not None,
                        "lock": lock,
                        "mismatch": mismatch,
                        "cleared": False,
                    },
                    message="Report only (force=false): lock not cleared",
                )

            audit = emergency_unlock_project_lock(
                db,
                project_id,
                force=True,
                reason=reason,
                mismatch=mismatch,
            )
            return SuccessResult(
                data={
                    "project_id": project_id,
                    "cleared": True,
                    "audit": audit,
                    "mismatch": mismatch,
                },
                message=f"Lock forcibly cleared for project {project_id}",
            )
        except Exception as e:
            return self._handle_error(
                e, "EMERGENCY_UNLOCK_PROJECT_ERROR", "emergency_unlock_project"
            )
        finally:
            db.disconnect()

    @classmethod
    def metadata(
        cls: type["EmergencyUnlockProjectMCPCommand"],
    ) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "emergency_unlock_project reports on, or force-clears, the "
                "whole-project exclusive lock (core/project_exclusive_lock.py, bugs "
                "88f06abc, 5da73265). It is the ONE command exempt from "
                "BaseMCPCommand.run()'s project-lock gate: PROJECT_LOCKED does NOT "
                "apply to this command itself, by design - it must be callable on a "
                "locked project.\n\n"
                "force=true does NOT reconcile disk vs DB for you: if rename_project's "
                "Step 2 (disk rename) succeeded but Step 3 (DB update) failed, the "
                "directory is already renamed on disk and the DB still points at the "
                "old name/path; you must fix the DB row yourself (or re-run "
                "rename_project once unlocked) after clearing the lock.\n\n"
                "Incident runbook:\n"
                "1. Call with force=false first to see the reported lock state plus "
                "the disk/DB mismatch report (db_root_path, whether it exists on "
                "disk, stored_name).\n"
                "2. Independently inspect the project's directory on disk "
                "(terminal/host-exec) to confirm which name/location is actually "
                "correct before clearing anything.\n"
                "3. Only call again with force=true and a specific reason once you "
                "have manually reconciled, or decided the lock is genuinely stuck "
                "(e.g. a crashed rename_project mid-flight).\n"
                "4. After clearing, if disk and DB disagree, fix the DB row yourself "
                "or re-run rename_project to bring them back into agreement."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID to inspect/unlock.",
                    "type": "string",
                    "required": True,
                },
                "force": {
                    "description": (
                        "Must be true to actually clear the lock. false (default "
                        "posture) only reports the lock state and mismatch; "
                        "clears nothing."
                    ),
                    "type": "boolean",
                    "required": True,
                },
                "reason": {
                    "description": (
                        "Why you are force-clearing this lock. Becomes part of "
                        "the structured audit log line."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "rename_project crashed mid-flight, disk and DB reconciled manually"
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Inspect a possibly-stuck lock (safe, no changes)",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "force": False,
                        "reason": "",
                    },
                    "explanation": (
                        "Reports whether the project is locked, by whom/why, and "
                        "whether the DB's resolved root path exists on disk."
                    ),
                },
                {
                    "description": "Force-clear a confirmed-stuck lock",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "force": True,
                        "reason": "rename_project crashed mid-flight; disk/DB reconciled manually",
                    },
                    "explanation": (
                        "Clears the lock and logs a structured audit line "
                        "including the previous lock row and the mismatch report."
                    ),
                },
            ],
            "error_cases": {
                "EMERGENCY_UNLOCK_PROJECT_ERROR": {
                    "description": "Unexpected error while inspecting or clearing the lock",
                    "example": "Database error during lookup or delete",
                    "solution": "Check server logs; retry once the underlying issue is resolved.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "project_id": "Project UUID",
                        "locked": "(force=false only) whether the project is currently locked",
                        "lock": "(force=false only) the lock row dict, or null if unlocked",
                        "mismatch": "Disk/DB mismatch report (db_root_path, db_root_exists_on_disk, stored_name)",
                        "cleared": "Whether the lock was actually cleared (false unless force=true)",
                        "audit": "(force=true only) audit record from emergency_unlock_project_lock",
                    },
                    "example": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "locked": True,
                        "lock": {
                            "project_id": "550e8400-e29b-41d4-a716-446655440000",
                            "locked_at": 1732000000.0,
                            "owner": "rename_project:abc123",
                            "reason": "rename_project to 'new_name'",
                        },
                        "mismatch": {
                            "db_root_path": "/watch/root/new_name",
                            "db_root_exists_on_disk": True,
                            "stored_name": "new_name",
                        },
                        "cleared": False,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "EMERGENCY_UNLOCK_PROJECT_ERROR",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Always call with force=false first to see the lock state and "
                "mismatch report before clearing anything",
                "Independently verify the project's directory on disk before "
                "force-clearing - this command does not reconcile disk vs DB for you",
                "Provide a specific, meaningful reason - it becomes part of the "
                "permanent structured audit log line",
                "After clearing a lock left by a failed rename_project, check "
                "whether the DB row needs manual correction or a re-run of "
                "rename_project",
            ],
        }
