"""
MCP command for batch runtime advisory file locks.

Each ``file_path`` is resolved under the registered watched project's ``root_path``
(``list_projects``), not under the code-analysis server install tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Type, cast

from mcp_proxy_adapter.commands.result import SuccessResult

from .base_mcp_command import BaseMCPCommand
from .base_mcp_command_resolve_path import resolve_under_project_root
from .project_file_advisory_lock_batch_metadata import (
    get_project_file_advisory_lock_batch_metadata,
)
from .project_file_advisory_lock_batch_schema import (
    get_project_file_advisory_lock_batch_schema,
)
from ..core.exceptions import ValidationError
from ..core.file_lock import acquire_persistent_file_lock, release_persistent_file_lock
from ..core.runtime_lock_sessions import (
    get_session_id_for_current_pid,
    normalize_lock_mode,
    register_runtime_session,
    runtime_session_exists,
)


class ProjectFileAdvisoryLockBatchCommand(BaseMCPCommand):
    """Acquire/release advisory file locks in a non-fail-fast batch."""

    name = "project_file_advisory_lock_batch"
    version = "1.0.0"
    descr = (
        "Batch lock/unlock files under a registered watched project (list_projects root_path) "
        "with runtime advisory leases."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_project_file_advisory_lock_batch_schema())

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        items = params.get("items")
        if not isinstance(items, list) or not items:
            raise ValidationError(
                "items must be a non-empty array",
                field="items",
                details={"items_type": type(items).__name__},
            )
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValidationError(
                    "each item must be an object",
                    field=f"items[{idx}]",
                    details={"item_type": type(item).__name__},
                )
            action = str(item.get("action") or "").strip()
            if action not in {"lock", "unlock"}:
                raise ValidationError(
                    "action must be lock or unlock",
                    field=f"items[{idx}].action",
                    details={"action": action},
                )
            for field in ("session_id", "project_id", "file_path"):
                if not str(item.get(field) or "").strip():
                    raise ValidationError(
                        f"{field} is required",
                        field=f"items[{idx}].{field}",
                        details={},
                    )
            if action == "lock":
                try:
                    normalize_lock_mode(item.get("lock_mode") or "full")
                except ValueError as exc:
                    raise ValidationError(
                        str(exc),
                        field=f"items[{idx}].lock_mode",
                        details={"lock_mode": item.get("lock_mode")},
                    ) from exc
                if str(item.get("lock_mode") or "full").strip() == "none":
                    raise ValidationError(
                        "lock_mode for lock items must be block_write or full",
                        field=f"items[{idx}].lock_mode",
                        details={"lock_mode": item.get("lock_mode")},
                    )
        return params

    @classmethod
    def metadata(cls: Type["ProjectFileAdvisoryLockBatchCommand"]) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_project_file_advisory_lock_batch_metadata(cls))

    async def execute(
        self,
        items: List[Dict[str, Any]],
        allow_foreign_session: bool = False,
        timeout_seconds: float | None = None,
        **kwargs: Any,
    ) -> SuccessResult:
        database = self._open_database_from_config(auto_analyze=False)
        current_session_id = get_session_id_for_current_pid(database, role="daemon")
        if not runtime_session_exists(database, current_session_id):
            register_runtime_session(
                database, role="daemon", session_id=current_session_id
            )

        results: List[Dict[str, Any]] = []
        for idx, item in enumerate(items):
            result_base = {
                "index": idx,
                "action": str(item.get("action") or "").strip(),
                "session_id": str(item.get("session_id") or "").strip(),
                "project_id": str(item.get("project_id") or "").strip(),
                "file_path": str(Path(str(item.get("file_path") or "")).as_posix()),
            }
            try:
                results.append(
                    self._execute_item(
                        database,
                        result_base,
                        item,
                        allow_foreign_session=bool(allow_foreign_session),
                        current_session_id=current_session_id,
                        timeout_seconds=timeout_seconds,
                    )
                )
            except Exception as exc:
                failed = dict(result_base)
                failed.update(
                    {
                        "ok": False,
                        "code": "ITEM_ERROR",
                        "message": str(exc),
                    }
                )
                results.append(failed)

        succeeded = sum(1 for item in results if item.get("ok") is True)
        return SuccessResult(
            data={
                "results": results,
                "total": len(results),
                "succeeded": succeeded,
                "failed": len(results) - succeeded,
                "current_session_id": current_session_id,
            }
        )

    def _execute_item(
        self,
        database: Any,
        base: Dict[str, Any],
        item: Dict[str, Any],
        *,
        allow_foreign_session: bool,
        current_session_id: str,
        timeout_seconds: float | None = None,
    ) -> Dict[str, Any]:
        session_id = base["session_id"]
        project_id = base["project_id"]
        file_path = base["file_path"]
        action = base["action"]

        if not runtime_session_exists(database, session_id):
            return self._item_error(
                base,
                "SESSION_NOT_FOUND",
                f"Runtime lock session not found: {session_id}",
            )
        if not allow_foreign_session and session_id != current_session_id:
            return self._item_error(
                base,
                "FOREIGN_SESSION_FORBIDDEN",
                "Foreign runtime lock session is not allowed",
            )

        project = database.get_project(project_id)
        if not project:
            return self._item_error(
                base,
                "PROJECT_NOT_FOUND",
                f"Project {project_id} not found",
            )
        root = Path(project.root_path).resolve()

        if action == "unlock":
            release_persistent_file_lock(
                session_id=session_id,
                project_id=project_id,
                file_path=file_path,
                database=database,
                force=True,
            )
            ok = dict(base)
            ok.update({"ok": True})
            return ok

        try:
            abs_path = resolve_under_project_root(
                root,
                file_path,
                require_exists=True,
                must_be_file=True,
            )
        except ValidationError as exc:
            return self._item_error(
                base,
                "FILE_NOT_FOUND",
                str(exc),
                details=getattr(exc, "details", None) or {},
            )
        row = database.get_file_by_path(
            str(abs_path), project_id, include_deleted=False
        )
        if not row:
            return self._item_error(
                base,
                "FILE_NOT_FOUND",
                f"Indexed file not found: {file_path}",
            )
        lock_mode = str(item.get("lock_mode") or "full").strip()
        handle = acquire_persistent_file_lock(
            abs_path,
            mode=lock_mode,
            database=database,
            project_id=project_id,
            file_path=file_path,
            session_id=session_id,
            timeout=timeout_seconds,
            register_role="daemon",
        )
        ok = dict(base)
        ok.update(
            {"ok": True, "lock_mode": lock_mode, "lock_path": str(handle.lock_path)}
        )
        return ok

    @staticmethod
    def _item_error(
        base: Dict[str, Any],
        code: str,
        message: str,
        *,
        details: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        item = dict(base)
        item.update({"ok": False, "code": code, "message": message})
        if details:
            item["details"] = details
        return item
