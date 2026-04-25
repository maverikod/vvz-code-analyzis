"""
Custom health command with dependency compatibility diagnostics.
"""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime
from typing import Any, Dict

import psutil
from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.result import SuccessResult
from mcp_proxy_adapter.core.proxy_registration import get_proxy_registration_status
from mcp_proxy_adapter.integrations.queuemgr_integration import (
    QUEUE_MANAGER_ENABLED_DEFAULT,
)

from code_analysis.core.dependency_compat import collect_dependency_compatibility


class HealthCommand(Command):
    """Health command extended with package version checks."""

    name = "health"
    descr = "Server health with queue dependency compatibility diagnostics"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    async def execute(self, **kwargs: Any) -> SuccessResult:
        process = psutil.Process(os.getpid())
        start_time = datetime.fromtimestamp(process.create_time())
        uptime_seconds = (datetime.now() - start_time).total_seconds()
        memory_info = process.memory_info()

        queue_cfg = (self._safe_get_queue_config() or {})
        queue_enabled = bool(
            queue_cfg.get("enabled", QUEUE_MANAGER_ENABLED_DEFAULT)
            if isinstance(queue_cfg, dict)
            else QUEUE_MANAGER_ENABLED_DEFAULT
        )
        dep = collect_dependency_compatibility(queue_enabled=queue_enabled)

        overall_status = "ok" if dep["queue_ready"] else "degraded"
        return SuccessResult(
            data={
                "status": overall_status,
                "version": dep["versions"]["code_analysis_server"],
                "uptime": uptime_seconds,
                "components": {
                    "system": {
                        "python_version": sys.version,
                        "platform": platform.platform(),
                        "cpu_count": os.cpu_count(),
                    },
                    "process": {
                        "pid": os.getpid(),
                        "memory_usage_mb": memory_info.rss / (1024 * 1024),
                        "start_time": start_time.isoformat(),
                    },
                    "commands": {"registered_count": len(registry.get_all_commands())},
                    "proxy_registration": get_proxy_registration_status(),
                    "queue_dependencies": dep,
                },
            }
        )

    @staticmethod
    def _safe_get_queue_config() -> Dict[str, Any]:
        try:
            from mcp_proxy_adapter.config import get_config

            cfg = get_config()
            if hasattr(cfg, "model") and hasattr(cfg.model, "queue_manager"):
                queue_obj = cfg.model.queue_manager
                if hasattr(queue_obj, "model_dump"):
                    dumped = queue_obj.model_dump()
                    if isinstance(dumped, dict):
                        return dumped
                if isinstance(queue_obj, dict):
                    return queue_obj
        except Exception:
            pass
        return {}
