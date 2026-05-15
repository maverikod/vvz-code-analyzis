"""
MCP command: list_yaml_blocks

List addressable YAML elements with stable ids (no session required).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

import yaml
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.file_lock import file_lock
from ..core.yaml_tree.tree_builder import build_yaml_tree_from_data

logger = logging.getLogger(__name__)


class ListYamlBlocksCommand(BaseMCPCommand):
    name = "list_yaml_blocks"
    version = "1.0.0"
    descr = (
        "List indexed YAML values (node_id, yaml_pointer, kind) for a .yaml/.yml file"
    )
    category = "yaml"
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
                    "description": "Path to .yaml or .yml relative to project root",
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

            if target.suffix.lower() not in (".yaml", ".yml"):
                return ErrorResult(
                    message="list_yaml_blocks only supports .yaml and .yml files",
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
                    doc = yaml.safe_load(raw)
                except yaml.YAMLError as e:
                    return ErrorResult(
                        message=f"Invalid YAML: {e}",
                        code="INVALID_YAML",
                        details={"error": str(e)},
                    )
                if doc is None:
                    doc = {}
                ephemeral = build_yaml_tree_from_data(
                    str(target.resolve()), doc, register=False
                )

            blocks = [
                {
                    "node_id": m.node_id,
                    "yaml_pointer": m.yaml_pointer,
                    "kind": m.kind,
                    "key": m.key,
                    "index": m.index,
                    "parent_id": m.parent_id,
                }
                for m in ephemeral.metadata_map.values()
            ]
            blocks.sort(key=lambda b: str(b["yaml_pointer"]))

            logger.info(
                "[TIMING] command=list_yaml_blocks blocks=%d elapsed_sec=%.4f",
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
            logger.exception("list_yaml_blocks failed: %s", e)
            return ErrorResult(
                message=f"list_yaml_blocks failed: {e}", code="YAML_LIST_ERROR"
            )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
        }
