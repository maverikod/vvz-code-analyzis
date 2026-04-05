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
from ..core.json_tree.json_saver import save_json_tree_to_file
from ..core.json_tree.tree_builder import reload_tree_from_file

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
            },
            "required": ["tree_id", "project_id", "file_path"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    async def execute(
        self,
        tree_id: str,
        project_id: str,
        file_path: str,
        backup: bool = True,
        commit_message: Optional[str] = None,
        auto_reload: bool = True,
        **kwargs: Any,
    ) -> SuccessResult:
        t_start = time.perf_counter()
        try:
            database = self._open_database_from_config(auto_analyze=False)
            try:
                absolute_path = self._resolve_file_path_from_project(
                    database, project_id, file_path
                )
                project = database.get_project(project_id)
                if not project:
                    return ErrorResult(
                        message=f"Project {project_id} not found",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )
                if absolute_path.suffix.lower() != ".json":
                    return ErrorResult(
                        message="json_save_tree only supports .json files",
                        code="INVALID_FILE",
                        details={"file_path": str(absolute_path)},
                    )
                root_dir = Path(project.root_path)

                blocked_venv = reject_if_write_under_project_venv(absolute_path, root_dir)
                if blocked_venv is not None:
                    return blocked_venv

                result = await asyncio.to_thread(
                    save_json_tree_to_file,
                    tree_id=tree_id,
                    file_path=str(absolute_path),
                    root_dir=root_dir,
                    project_id=project_id,
                    database=database,
                    backup=backup,
                    commit_message=commit_message,
                )
            finally:
                database.disconnect()

            if not result.get("success"):
                return ErrorResult(
                    message=result.get("error", "json_save_tree failed"),
                    code="JSON_SAVE_ERROR",
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
    def metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
        }
