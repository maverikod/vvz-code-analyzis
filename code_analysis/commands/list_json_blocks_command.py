"""
MCP command: list_json_blocks

List addressable JSON elements with stable ids (no session required).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.file_lock import file_lock
from ..core.json_tree.tree_builder import build_tree_from_data

logger = logging.getLogger(__name__)


class ListJsonBlocksCommand(BaseMCPCommand):
    name = "list_json_blocks"
    version = "1.0.0"
    descr = "List indexed JSON values (node_id, json_pointer, kind) for a .json file"
    category = "json"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        base = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base,
                "file_path": {
                    "type": "string",
                    "description": "Path to .json relative to project root",
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    async def execute(
        self, project_id: str, file_path: str, **kwargs: Any
    ) -> SuccessResult:
        t_start = time.perf_counter()
        try:
            database = self._open_database_from_config(auto_analyze=False)
            try:
                target = self._resolve_file_path_from_project(
                    database, project_id, file_path
                )
            finally:
                database.disconnect()

            if target.suffix.lower() != ".json":
                return ErrorResult(
                    message="list_json_blocks only supports .json files",
                    code="INVALID_FILE",
                    details={"file_path": str(target)},
                )
            if not target.exists():
                return ErrorResult(
                    message="File not found",
                    code="FILE_NOT_FOUND",
                    details={"file_path": str(target)},
                )

            with file_lock(target):
                raw = target.read_text(encoding="utf-8")
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError as e:
                    return ErrorResult(
                        message=f"Invalid JSON: {e}",
                        code="INVALID_JSON",
                        details={"error": str(e)},
                    )
                ephemeral = build_tree_from_data(
                    str(target.resolve()), data, register=False
                )

            blocks = [
                {
                    "node_id": m.node_id,
                    "json_pointer": m.json_pointer,
                    "kind": m.kind,
                    "key": m.key,
                    "index": m.index,
                    "parent_id": m.parent_id,
                }
                for m in ephemeral.metadata_map.values()
            ]
            blocks.sort(key=lambda b: str(b["json_pointer"]))

            logger.info(
                "[TIMING] command=list_json_blocks blocks=%d elapsed_sec=%.4f",
                len(blocks),
                time.perf_counter() - t_start,
            )
            return SuccessResult(
                data={
                    "success": True,
                    "file_path": str(target.resolve()),
                    "blocks": blocks,
                    "total_blocks": len(blocks),
                }
            )
        except Exception as e:
            logger.exception("list_json_blocks failed: %s", e)
            return ErrorResult(
                message=f"list_json_blocks failed: {e}", code="JSON_LIST_ERROR"
            )

    @classmethod
    def metadata(cls: type["ListJsonBlocksCommand"]) -> Dict[str, Any]:
        from .json_tree_commands_metadata import json_tree_command_metadata

        return json_tree_command_metadata(
            cls,
            operation="list_blocks",
            detailed_description=cls.descr,
            example_params={
                "project_id": "550e8400-e29b-41d4-a716-446655440000",
                "file_path": "config/settings.json",
            },
            extra_errors={"JSON_LIST_ERROR": {"description": "Failed to list blocks."}},
        )
