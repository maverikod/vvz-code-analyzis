"""
MCP command: UUID identity migration (admin / maintenance).

**Destructive paths (phase 6 swap) require a maintenance window, verified backup, and no
concurrent writers.** Default actions are non-destructive (preflight, dry-run phases 3–5).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.core.database.migrations import (
    Phase345Report,
    run_uuid_migration_phase2_build_mappings,
    run_uuid_migration_phase6_swap_postgres,
    run_uuid_migration_phase6_swap_sqlite,
    run_uuid_migration_phases_3_to_5_postgres,
    run_uuid_migration_phases_3_to_5_sqlite,
    run_uuid_migration_preflight_phase1,
)
from code_analysis.core.database.migrations.uuid_identity_migration_common import (
    Phase2Report,
    PreflightReport,
    detect_backend_kind,
)

from ..base_mcp_command import BaseMCPCommand

_ACTIONS = frozenset(
    {
        "preflight",
        "phase2_mappings",
        "phases_345",
        "phase6_swap",
        "pipeline_dry",
    }
)

_MAX_SQL_LOG_STMTS_IN_RESPONSE = 40


def _executed_via_job_queue(context: Any) -> bool:
    """True when ``execute`` is invoked from mcp_proxy_adapter's queue worker (not HTTP sync)."""
    return isinstance(context, dict) and context.get("progress_tracker") is not None


def _json_safe(obj: Any) -> Any:
    """Convert dataclass payloads to JSON-serializable primitive values."""
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _preflight_to_dict(r: PreflightReport) -> Dict[str, Any]:
    """Serialize a phase 1 preflight report for the MCP response."""
    return cast(Dict[str, Any], _json_safe(asdict(r)))


def _phase2_to_dict(r: Phase2Report) -> Dict[str, Any]:
    """Serialize a phase 2 mapping-build report for the MCP response."""
    return cast(Dict[str, Any], _json_safe(asdict(r)))


def _phase345_to_dict(r: Phase345Report) -> Dict[str, Any]:
    """Serialize phases 3-5 report and truncate long SQL logs."""
    d = asdict(r)
    log: List[str] = list(d.get("sql_log") or [])
    total = len(log)
    truncated = total > _MAX_SQL_LOG_STMTS_IN_RESPONSE
    if truncated:
        d["sql_log"] = log[:_MAX_SQL_LOG_STMTS_IN_RESPONSE]
    else:
        d["sql_log"] = log
    d["sql_log_statement_count"] = total
    d["sql_log_truncated"] = truncated
    return cast(Dict[str, Any], _json_safe(d))


def _phase6_stmts_to_dict(stmts: List[str]) -> Dict[str, Any]:
    """Serialize phase 6 rename statements with response-size limits."""
    total = len(stmts)
    truncated = total > _MAX_SQL_LOG_STMTS_IN_RESPONSE
    out = stmts[:_MAX_SQL_LOG_STMTS_IN_RESPONSE] if truncated else stmts
    return {
        "rename_statements": _json_safe(out),
        "rename_statement_count": total,
        "rename_statements_truncated": truncated,
    }


class RunUuidIdentityMigrationMCPCommand(BaseMCPCommand):
    """Run UUID identity migration steps against the configured shared database (admin)."""

    name = "run_uuid_identity_migration"
    version = "1.0.0"
    descr = (
        "UUID identity migration (preflight, mapping build, phases 3–5, optional phase 6 swap). "
        "Runs only via the job queue (background worker); long-running DB work must not block HTTP. "
        "Default paths are non-destructive; phase 6 requires explicit confirmation."
    )
    category = "database_admin"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = (
        True  # pipeline_dry / phase2 / phases_345 can exceed HTTP handler timeouts
    )

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": sorted(_ACTIONS),
                    "description": (
                        "preflight: Phase 1 only; phase2_mappings: build uuid_migration_* maps; "
                        "phases_345: shadow copy + validate (honors dry_run); phase6_swap: "
                        "destructive rename swap (requires i_confirm_maintenance_swap); "
                        "pipeline_dry: preflight + phase2 + phases_345 with dry_run=true."
                    ),
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "For phases_345 only: if true, SQL is logged but not executed.",
                    "default": True,
                },
                "skip_mapping_validation": {
                    "type": "boolean",
                    "description": "Skip mapping table validation before phases 3–5.",
                    "default": False,
                },
                "shadow_prefix": {
                    "type": "string",
                    "description": "Optional shadow table prefix (implementation default if omitted).",
                },
                "migration_tag": {
                    "type": "string",
                    "description": "Optional tag for phase 6 backup table suffix (backend default if omitted).",
                },
                "i_confirm_maintenance_swap": {
                    "type": "boolean",
                    "description": "Must be true for phase6_swap after backup and maintenance window.",
                    "default": False,
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        }

    def _p345_kwargs(
        self,
        *,
        dry_run: bool,
        skip_mapping_validation: bool,
        shadow_prefix: Optional[str],
    ) -> Dict[str, Any]:
        """Build keyword arguments for phases 3-5 migration helpers."""
        kw: Dict[str, Any] = {
            "dry_run": dry_run,
            "skip_mapping_validation": skip_mapping_validation,
        }
        if shadow_prefix is not None:
            kw["shadow_prefix"] = shadow_prefix
        return kw

    def _phase6_kwargs(
        self,
        *,
        shadow_prefix: Optional[str],
        migration_tag: Optional[str],
        i_confirm_maintenance_swap: bool,
    ) -> Dict[str, Any]:
        """Build keyword arguments for destructive phase 6 swap helpers."""
        kw: Dict[str, Any] = {
            "i_confirm_maintenance_swap": i_confirm_maintenance_swap,
        }
        if shadow_prefix is not None:
            kw["shadow_prefix"] = shadow_prefix
        if migration_tag is not None:
            kw["migration_tag"] = migration_tag
        return kw

    async def execute(
        self,
        action: str,
        dry_run: bool = True,
        skip_mapping_validation: bool = False,
        shadow_prefix: Optional[str] = None,
        migration_tag: Optional[str] = None,
        i_confirm_maintenance_swap: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Run the requested UUID migration action through the job-queue path."""
        if action not in _ACTIONS:
            return ErrorResult(
                message=f"Invalid action {action!r}; expected one of {sorted(_ACTIONS)}",
                code="UUID_MIGRATION_INVALID_ACTION",
                details={"action": action},
            )

        if action == "phase6_swap" and not i_confirm_maintenance_swap:
            return ErrorResult(
                message=(
                    "phase6_swap refused: set i_confirm_maintenance_swap=True only after a full "
                    "backup, maintenance window, and stopping all writers."
                ),
                code="UUID_MIGRATION_CONFIRMATION_REQUIRED",
                details={"action": action},
            )

        context = kwargs.get("context")
        if not _executed_via_job_queue(context):
            return ErrorResult(
                message=(
                    "run_uuid_identity_migration must run in the job queue only (background worker). "
                    "Submit the command through the server's queued execution path "
                    "(class use_queue=True) and poll queue_get_job_status / queue_get_job_logs; "
                    "inline HTTP execution is not supported."
                ),
                code="UUID_MIGRATION_QUEUE_REQUIRED",
                details={"action": action},
            )

        database = self._open_database_from_config(auto_analyze=False)
        try:
            backend = detect_backend_kind(database)
            payload: Dict[str, Any] = {
                "action": action,
                "backend": backend,
                "steps": [],
                "errors": [],
            }

            if action == "preflight":
                rep = run_uuid_migration_preflight_phase1(database)
                payload["steps"].append(
                    {"step": "preflight_phase1", "report": _preflight_to_dict(rep)}
                )
                return SuccessResult(data=payload)

            if action == "phase2_mappings":
                rep2 = run_uuid_migration_phase2_build_mappings(database)
                payload["steps"].append(
                    {"step": "phase2_mappings", "report": _phase2_to_dict(rep2)}
                )
                return SuccessResult(data=payload)

            if action == "phases_345":
                kw = self._p345_kwargs(
                    dry_run=dry_run,
                    skip_mapping_validation=skip_mapping_validation,
                    shadow_prefix=shadow_prefix,
                )
                if backend == "sqlite":
                    r345 = run_uuid_migration_phases_3_to_5_sqlite(database, **kw)
                elif backend == "postgresql":
                    r345 = run_uuid_migration_phases_3_to_5_postgres(database, **kw)
                else:
                    return ErrorResult(
                        message=f"Unsupported backend for phases 3–5: {backend!r}",
                        code="UUID_MIGRATION_UNSUPPORTED_BACKEND",
                        details={"backend": backend},
                    )
                payload["steps"].append(
                    {"step": "phases_345", "report": _phase345_to_dict(r345)}
                )
                return SuccessResult(data=payload)

            if action == "phase6_swap":
                kw6 = self._phase6_kwargs(
                    shadow_prefix=shadow_prefix,
                    migration_tag=migration_tag,
                    i_confirm_maintenance_swap=i_confirm_maintenance_swap,
                )
                if backend == "sqlite":
                    stmts = run_uuid_migration_phase6_swap_sqlite(database, **kw6)
                elif backend == "postgresql":
                    stmts = run_uuid_migration_phase6_swap_postgres(database, **kw6)
                else:
                    return ErrorResult(
                        message=f"Unsupported backend for phase 6: {backend!r}",
                        code="UUID_MIGRATION_UNSUPPORTED_BACKEND",
                        details={"backend": backend},
                    )
                payload["steps"].append(
                    {"step": "phase6_swap", "report": _phase6_stmts_to_dict(stmts)}
                )
                return SuccessResult(data=payload)

            # pipeline_dry
            rep_pre = run_uuid_migration_preflight_phase1(database)
            payload["steps"].append(
                {"step": "preflight_phase1", "report": _preflight_to_dict(rep_pre)}
            )
            rep2 = run_uuid_migration_phase2_build_mappings(
                database, skip_preflight=True
            )
            payload["steps"].append(
                {"step": "phase2_mappings", "report": _phase2_to_dict(rep2)}
            )
            kw = self._p345_kwargs(
                dry_run=True,
                skip_mapping_validation=skip_mapping_validation,
                shadow_prefix=shadow_prefix,
            )
            if backend == "sqlite":
                r345 = run_uuid_migration_phases_3_to_5_sqlite(database, **kw)
            elif backend == "postgresql":
                r345 = run_uuid_migration_phases_3_to_5_postgres(database, **kw)
            else:
                return ErrorResult(
                    message=f"Unsupported backend for pipeline_dry: {backend!r}",
                    code="UUID_MIGRATION_UNSUPPORTED_BACKEND",
                    details={"backend": backend},
                )
            payload["steps"].append(
                {"step": "phases_345", "report": _phase345_to_dict(r345)}
            )
            return SuccessResult(data=payload)

        except Exception as e:
            return self._handle_error(
                e, "UUID_MIGRATION_ERROR", "run_uuid_identity_migration"
            )
        finally:
            database.disconnect()

    @classmethod
    def metadata(cls: type["RunUuidIdentityMigrationMCPCommand"]) -> Dict[str, Any]:
        """Return detailed safety-focused metadata for the migration command."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "Administrative UUID identity migration for the single shared database from server "
                "config. **Stop writers, take a backup, and plan a maintenance window before any "
                "non-dry-run data migration or phase 6.** phase6_swap is refused unless "
                "i_confirm_maintenance_swap is true.\n\n"
                "Execution is **only** allowed from the job queue (background worker): "
                "``use_queue=True`` on the command class; the handler enqueues and returns "
                "``job_id``. Inline synchronous execution is rejected (``UUID_MIGRATION_QUEUE_REQUIRED``). "
                "Poll ``queue_get_job_status`` / ``queue_get_job_logs`` until ``status`` is terminal; "
                "then read ``result.command.result`` — ``completed`` alone is not enough if the "
                "inner command returned an error."
            ),
            "parameters": cls.get_schema().get("properties", {}),
        }
