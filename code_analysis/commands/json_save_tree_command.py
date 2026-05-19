"""
MCP command: json_save_tree

Write JSON session to disk (atomic + backup + DB sync).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .project_text_file_guard import reject_if_write_under_project_venv
from ..core.git_integration import commit_after_write
from ..core.json_tree.json_saver import save_json_tree_to_file
from ..core.json_tree.tree_builder import get_tree, reload_tree_from_file

logger = logging.getLogger(__name__)


class JsonSaveTreeCommand(BaseMCPCommand):
    name = "json_save_tree"
    version = "1.0.0"
    descr = "Save JSON tree to .json file with backup and DB file_data update"
    category = "json"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tree_id": {"type": "string"},
                "project_id": {"type": "string"},
                "file_path": {
                    "type": "string",
                    "description": "Path relative to project root (.json)",
                },
                "backup": {"type": "boolean", "default": True},
                "commit_message": {"type": "string"},
                "auto_reload": {
                    "type": "boolean",
                    "default": True,
                    "description": "Reload session from disk after save (keeps tree_id)",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, validate tree_id and path only; no disk write or DB file update"
                    ),
                },
            },
            "required": ["tree_id", "project_id", "file_path"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    @staticmethod
    def _validate_relative_json_path(file_path: str) -> tuple[Path, str] | ErrorResult:
        raw_path = (file_path or "").strip()
        if not raw_path:
            return ErrorResult(
                code="INVALID_FILE_PATH",
                message="file_path must be a non-empty relative path.",
            )

        rel_path = Path(raw_path)
        if rel_path.is_absolute():
            return ErrorResult(
                code="INVALID_FILE_PATH",
                message="Absolute file_path is not allowed. Use project-relative path.",
            )
        if any(part == ".." for part in rel_path.parts):
            return ErrorResult(
                code="INVALID_FILE_PATH",
                message="Path traversal is not allowed in file_path.",
            )

        return rel_path, raw_path

    async def execute(
        self,
        tree_id: str,
        project_id: str,
        file_path: str,
        backup: bool = True,
        commit_message: Optional[str] = None,
        auto_reload: bool = True,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> SuccessResult:
        t_start = time.perf_counter()
        try:
            database = self._open_database_from_config(auto_analyze=False)
            try:
                validated_path = self._validate_relative_json_path(file_path)
                if isinstance(validated_path, ErrorResult):
                    return validated_path
                rel_path, raw_path = validated_path

                project = database.get_project(project_id)
                if not project:
                    return ErrorResult(
                        message=f"Project {project_id} not found",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )
                root_dir = Path(project.root_path).resolve()
                absolute_path = (root_dir / rel_path).resolve()
                try:
                    absolute_path.relative_to(root_dir)
                except ValueError:
                    return ErrorResult(
                        code="INVALID_FILE_PATH",
                        message="Resolved path escapes project root.",
                        details={
                            "file_path": raw_path,
                            "resolved_path": str(absolute_path),
                            "root_dir": str(root_dir),
                        },
                    )
                if not absolute_path.exists():
                    return ErrorResult(
                        message=f"File does not exist: {absolute_path}",
                        code="FILE_NOT_FOUND",
                        details={"file_path": str(absolute_path)},
                    )
                if not absolute_path.is_file():
                    return ErrorResult(
                        message=f"Path is not a file: {absolute_path}",
                        code="INVALID_FILE",
                        details={"file_path": str(absolute_path)},
                    )
                if absolute_path.suffix.lower() != ".json":
                    return ErrorResult(
                        message="json_save_tree only supports .json files",
                        code="INVALID_FILE",
                        details={"file_path": str(absolute_path)},
                    )

                blocked_venv = reject_if_write_under_project_venv(
                    absolute_path, root_dir
                )
                if blocked_venv is not None:
                    return blocked_venv

                if dry_run:
                    tree = get_tree(tree_id)
                    if not tree:
                        return ErrorResult(
                            message=f"Tree not found: {tree_id}",
                            code="TREE_NOT_FOUND",
                            details={"tree_id": tree_id},
                        )
                    try:
                        rel = str(absolute_path.relative_to(root_dir))
                    except ValueError:
                        rel = str(absolute_path)
                    payload = {
                        "success": True,
                        "dry_run": True,
                        "tree_id": tree_id,
                        "project_id": project_id,
                        "file_path": rel,
                        "resolved_path": str(absolute_path),
                    }
                    logger.info(
                        "[TIMING] command=json_save_tree dry_run elapsed_sec=%.4f",
                        time.perf_counter() - t_start,
                    )
                    return SuccessResult(data=payload)

                result = await asyncio.to_thread(
                    save_json_tree_to_file,
                    tree_id=tree_id,
                    file_path=str(absolute_path),
                    root_dir=root_dir,
                    project_id=project_id,
                    database=database,
                    backup=backup,
                )
            finally:
                database.disconnect()

            if not result.get("success"):
                return ErrorResult(
                    message=result.get("error", "json_save_tree failed"),
                    code=result.get("error_code", "JSON_SAVE_ERROR"),
                    details=result,
                )

            if auto_reload:
                try:
                    reload_tree_from_file(tree_id=tree_id)
                    result["tree_reloaded"] = True
                except Exception as e:
                    logger.warning("json_save_tree auto_reload failed: %s", e)
                    result["tree_reloaded"] = False
                    result["reload_error"] = str(e)

            cm = (
                commit_message.strip()
                if isinstance(commit_message, str) and commit_message.strip()
                else None
            )
            git_ok, git_err = commit_after_write(
                root_dir,
                [absolute_path],
                "json_save_tree",
                commit_message_override=cm,
                config_data=BaseMCPCommand._get_raw_config(),
            )
            if not git_ok and git_err:
                logger.warning("Git commit after json_save_tree: %s", git_err)

            logger.info(
                "[TIMING] command=json_save_tree elapsed_sec=%.4f",
                time.perf_counter() - t_start,
            )
            return SuccessResult(data={"success": True, **result})
        except Exception as e:
            logger.exception("json_save_tree failed: %s", e)
            return ErrorResult(
                message=f"json_save_tree failed: {e}", code="JSON_SAVE_ERROR"
            )

    @classmethod
    def metadata(cls: type["JsonSaveTreeCommand"]) -> Dict[str, Any]:
        from .json_tree_commands_metadata import json_tree_command_metadata

        return json_tree_command_metadata(
            cls,
            operation="save_tree",
            detailed_description=cls.descr,
            example_params={
                "tree_id": "550e8400-e29b-41d4-a716-446655440000",
                "project_id": "550e8400-e29b-41d4-a716-446655440001",
                "file_path": "config/settings.json",
            },
        )
