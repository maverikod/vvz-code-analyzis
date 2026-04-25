"""
Queue health command with dependency compatibility diagnostics.
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult
from mcp_proxy_adapter.integrations.queuemgr_integration import (
    QUEUE_MANAGER_ENABLED_DEFAULT,
    get_global_queue_manager,
)

from code_analysis.core.dependency_compat import collect_dependency_compatibility


class QueueHealthCommand(Command):
    """Queue health with dependency version diagnostics."""

    name = "queue_health"
    descr = "Queue subsystem health including dependency compatibility"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any):
        queue_cfg = self._safe_get_queue_config()
        queue_enabled = bool(queue_cfg.get("enabled", QUEUE_MANAGER_ENABLED_DEFAULT))
        dep = collect_dependency_compatibility(queue_enabled=queue_enabled)

        if queue_enabled and not dep["queue_ready"]:
            return ErrorResult(
                code="QUEUE_DEPENDENCY_INCOMPATIBLE",
                message="Queue subsystem dependencies are incompatible.",
                details=dep,
            )

        try:
            queue_manager = await get_global_queue_manager()
            health = await queue_manager.get_queue_health()
            health["dependency_versions"] = dep["versions"]
            health["dependency_minimum_required"] = dep["minimum_required"]
            health["dependency_compatibility"] = dep["compatibility"]
            health["queue_dependency_errors"] = dep["errors"]
            if dep["errors"]:
                health["status"] = "unhealthy"
            return SuccessResult(data=health)
        except Exception as e:
            return ErrorResult(
                message=f"Failed to check queue health: {str(e)}",
                code=-32603,
                details={"dependency_check": dep},
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
