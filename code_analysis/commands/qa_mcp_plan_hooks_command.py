"""
Deterministic MCP hooks for DB retry and project_activity_locks verification.

Enabled when ``CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1`` **or** root
``enable_qa_mcp_hooks: true`` in ``config.json`` (main sets the env at startup).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.database_driver_pkg.domain.projects import get_project
from ..core.qa_mcp_hooks_policy import qa_mcp_hooks_enabled_for_mcp_commands
from ..core.worker_project_activity import (
    release_project_activity,
    try_acquire_project_activity,
)
from .base_mcp_command import BaseMCPCommand


class QAMcpPlanHooksCommand(BaseMCPCommand):
    """Exercise ``[DB_RETRY]`` (via synthetic driver transients) and ``[WORKER_COORD]``."""

    name = "qa_mcp_plan_hooks"
    version = "1.0.0"
    descr = (
        "QA: deterministic db-retry injection + project activity lock contention; "
        "enable via env CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1 or config enable_qa_mcp_hooks"
    )
    category = "monitoring"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the schema for selecting deterministic QA hook scenarios."""
        return {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "enum": ["db_retry", "worker_coord", "both"],
                    "default": "both",
                },
                "inject_remaining": {
                    "type": "integer",
                    "default": 1,
                    "minimum": 0,
                    "maximum": 20,
                },
                "project_id": {
                    "type": "string",
                    "description": "Required for worker_coord / both (existing project id)",
                },
                "trigger_touch_project_row": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true (db_retry / both), run a no-op UPDATE on projects after arming injections",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    async def execute(
        self,
        scenario: str = "both",
        inject_remaining: int = 1,
        project_id: Optional[str] = None,
        trigger_touch_project_row: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Exercise configured DB retry and worker-coordination QA hooks."""
        if not qa_mcp_hooks_enabled_for_mcp_commands():
            return ErrorResult(
                message=(
                    "QA MCP hooks disabled; set CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1 "
                    "or enable_qa_mcp_hooks in config.json and restart the server"
                ),
                code="QA_MCP_HOOKS_DISABLED",
            )
        scenario_l = (scenario or "both").strip().lower()
        if scenario_l not in ("db_retry", "worker_coord", "both"):
            return ErrorResult(
                message="invalid scenario",
                code="QA_MCP_INVALID_SCENARIO",
                details={"scenario": scenario},
            )
        out: Dict[str, Any] = {"scenario": scenario_l, "steps": []}

        db = self._open_database_from_config(auto_analyze=False)
        try:
            if scenario_l in ("db_retry", "both"):
                arm = db.qa_set_db_retry_injections(int(inject_remaining))
                out["steps"].append({"qa_set_db_retry_injections": arm})
                if trigger_touch_project_row:
                    if not project_id or not str(project_id).strip():
                        return ErrorResult(
                            message="project_id is required when trigger_touch_project_row is true",
                            code="QA_MCP_MISSING_PROJECT_ID",
                            details={"scenario": scenario_l},
                        )
                    pid = str(project_id).strip()
                    proj = get_project(db, pid)
                    if not proj:
                        return ErrorResult(
                            message="project not found",
                            code="QA_MCP_PROJECT_NOT_FOUND",
                            details={"project_id": pid},
                        )
                    touch_sql = "UPDATE projects SET name = name WHERE id = ?"
                    touch = db.execute(touch_sql, (pid,), transaction_id=None)
                    out["steps"].append({"touch_write": touch})

            if scenario_l in ("worker_coord", "both"):
                if not project_id or not str(project_id).strip():
                    return ErrorResult(
                        message="project_id is required for worker_coord",
                        code="QA_MCP_MISSING_PROJECT_ID",
                        details={"scenario": scenario_l},
                    )
                pid = str(project_id).strip()
                proj = get_project(db, pid)
                if not proj:
                    return ErrorResult(
                        message=f"Project {pid} not found",
                        code="QA_MCP_PROJECT_NOT_FOUND",
                        details={"project_id": pid},
                    )
                owner_a = "mcp_qa_plan_hook_a"
                owner_b = "mcp_qa_plan_hook_b"
                ttl = 120.0
                act = "command_mutation"
                ok_a = try_acquire_project_activity(
                    db, pid, "command", owner_a, act, ttl
                )
                ok_b = try_acquire_project_activity(
                    db, pid, "command", owner_b, act, ttl
                )
                out["steps"].append(
                    {
                        "try_acquire_a": ok_a,
                        "try_acquire_b": ok_b,
                        "expected": "first True, second False when lease held",
                    }
                )
                release_project_activity(db, pid, "command", owner_a)
                release_project_activity(db, pid, "command", owner_b)
                out["steps"].append({"released": [owner_a, owner_b]})

            out["success"] = True
            out["log_hint"] = (
                "Search driver / worker logs for [DB_RETRY] and [WORKER_COORD] "
                "(e.g. view_worker_logs) after this call."
            )
            return SuccessResult(data=out)
        except Exception as e:
            return self._handle_error(e, "QA_MCP_PLAN_HOOKS_ERROR", "qa_mcp_plan_hooks")
        finally:
            db.disconnect()

    @classmethod
    def metadata(cls: type["QAMcpPlanHooksCommand"]) -> Dict[str, Any]:
        """Return registration metadata for the QA hook command."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "schema": cls.get_schema(),
        }
