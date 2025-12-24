"""
MCP commands to manage dynamic watch directories for the vectorization worker.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Dict, Any, List

from mcp_proxy_adapter.commands.base import Command, CommandResult
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult


def _load_dynamic_watch_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"watch_dirs": []}
    import json

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_dynamic_watch_file(path: Path, data: Dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


class AddWatchDirCommand(Command):
    """
    ADD_WATCH_DIR - Add a dynamic watch directory for the vectorization worker.
    """

    name = "add_watch_dir"
    descr = "Add a dynamic watch directory for the vectorization worker"
    version = "1.0.0"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to watch"},
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def execute(self, path: str, **kwargs) -> CommandResult:
        if not path:
            return ErrorResult("path is required")

        context = kwargs.get("context") or {}
        app_config = context.get("config") or context.get("app_config") or {}
        config = app_config.get("code_analysis") or app_config
        worker_cfg = config.get("worker", {})
        dyn_file = worker_cfg.get("dynamic_watch_file", "data/dynamic_watch_dirs.json")
        dyn_path = Path(dyn_file)

        data = _load_dynamic_watch_file(dyn_path)
        watch_dirs: List[str] = data.get("watch_dirs", [])
        if path not in watch_dirs:
            watch_dirs.append(path)
            data["watch_dirs"] = watch_dirs
            _save_dynamic_watch_file(dyn_path, data)

        return SuccessResult({"watch_dirs": watch_dirs})


class RemoveWatchDirCommand(Command):
    """
    REMOVE_WATCH_DIR - Remove a dynamic watch directory from the vectorization worker.
    """

    name = "remove_watch_dir"
    descr = "Remove a dynamic watch directory from the vectorization worker"
    version = "1.0.0"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to remove"},
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    async def execute(self, path: str, **kwargs) -> CommandResult:
        if not path:
            return ErrorResult("path is required")

        context = kwargs.get("context") or {}
        app_config = context.get("config") or context.get("app_config") or {}
        config = app_config.get("code_analysis") or app_config
        worker_cfg = config.get("worker", {})
        dyn_file = worker_cfg.get("dynamic_watch_file", "data/dynamic_watch_dirs.json")
        dyn_path = Path(dyn_file)

        data = _load_dynamic_watch_file(dyn_path)
        watch_dirs: List[str] = data.get("watch_dirs", [])
        if path in watch_dirs:
            watch_dirs = [p for p in watch_dirs if p != path]
            data["watch_dirs"] = watch_dirs
            _save_dynamic_watch_file(dyn_path, data)

        return SuccessResult({"watch_dirs": watch_dirs})

