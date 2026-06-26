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
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult
from mcp_proxy_adapter.core.errors import ValidationError
from mcp_proxy_adapter.core.proxy_registration import get_proxy_registration_status
from mcp_proxy_adapter.integrations.queuemgr_integration import (
    QUEUE_MANAGER_ENABLED_DEFAULT,
)

from code_analysis.core.cst_tree.tree_builder import _trees
from code_analysis.core.dependency_compat import collect_dependency_compatibility


class HealthCommand(Command):
    """Health command extended with package version checks."""

    name = "health"
    version = "1.0.0"
    descr = "Server health with queue dependency compatibility diagnostics"
    category = "system"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        from code_analysis.commands.command_metadata_helpers import empty_params_schema

        return empty_params_schema(
            description="No parameters; returns server and dependency health.",
        )

    @classmethod
    def metadata(cls: type["HealthCommand"]) -> Dict[str, Any]:
        """Return metadata for the zero-argument health command."""
        from code_analysis.commands.zero_arg_commands_metadata import (
            health_command_metadata,
        )

        return health_command_metadata(cls)

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Adapter Command validates unknown keys; server execute path calls this explicitly."""
        return super().validate_params(params)

    async def execute(self, **kwargs: Any) -> SuccessResult | ErrorResult:
        """Return process, configuration, queue, dependency, and quality-tool health."""
        params = {k: v for k, v in kwargs.items() if k != "context"}
        try:
            self.validate_params(params)
        except ValidationError as e:
            data = getattr(e, "data", None) or {}
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details={"field": data.get("field")},
            )
        process = psutil.Process(os.getpid())
        start_time = datetime.fromtimestamp(process.create_time())
        uptime_seconds = (datetime.now() - start_time).total_seconds()
        memory_info = process.memory_info()

        queue_cfg = self._safe_get_queue_config() or {}
        queue_enabled = bool(
            queue_cfg.get("enabled", QUEUE_MANAGER_ENABLED_DEFAULT)
            if isinstance(queue_cfg, dict)
            else QUEUE_MANAGER_ENABLED_DEFAULT
        )
        dep = collect_dependency_compatibility(queue_enabled=queue_enabled)

        from code_analysis.core.config_state import get_config_runtime_state

        cfg_state = get_config_runtime_state()
        config_ok = cfg_state.valid

        if not config_ok:
            overall_status = "config_error"
        elif dep["queue_ready"]:
            overall_status = "ok"
        else:
            overall_status = "degraded"
        return SuccessResult(
            data={
                "status": overall_status,
                "version": dep["versions"]["code_analysis_server"],
                "uptime": uptime_seconds,
                "cst_trees_loaded": len(_trees),
                "components": {
                    "configuration": cfg_state.summary(),
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
                    "quality_tools": self._quality_tools_health(),
                },
            }
        )

    @staticmethod
    def _quality_tools_health() -> Dict[str, Any]:
        """Availability + pinned versions of the code-quality tools (A-IMG.4).

        Surfaces flake8/mypy/black/isort/bandit status so a missing or stale tool
        is visible from ``health`` without shelling into the container.
        """
        try:
            from code_analysis.core.code_quality import quality_tool_report

            report = quality_tool_report()
            missing = sorted(t for t, v in report.items() if not v.get("available"))
            return {
                "status": "ok" if not missing else "degraded",
                "missing": missing,
                "tools": report,
            }
        except Exception as exc:  # never let health fail on the probe
            return {"status": "unknown", "error": str(exc)}

    @staticmethod
    def _safe_get_queue_config() -> Dict[str, Any]:
        """Read queue-manager config without allowing config errors to break health."""
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
