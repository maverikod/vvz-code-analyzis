"""
Handler for query_cst command: validation, replace ops building, and replace flow.

Used by QueryCSTCommand to keep the command file under size limit.
Replaces logic is applied here; command delegates and keeps schema/entry point.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.backup_manager import BackupManager
from ..core.cst_module import ReplaceOp, Selector, apply_replace_ops, unified_diff
from ..core.exceptions import CSTModulePatchError

logger = logging.getLogger(__name__)


def _write_replace_result_atomically(
    command: Any,
    root_path: Path,
    target: Path,
    new_source: str,
    project_id: str,
) -> Tuple[Optional[str], Optional[ErrorResult]]:
    """
    Write replace result with atomic filesystem swap and rollback on DB failure.

    Returns:
        (backup_uuid, None) on success
        (backup_uuid_or_none, ErrorResult) on failure
    """
    backup_manager = BackupManager(root_path)
    backup_uuid = backup_manager.create_backup(
        target,
        command="query_cst_replace",
        comment="",
    )
    if not backup_uuid:
        return None, ErrorResult(
            message="Backup to old_code is mandatory before write; create_backup failed",
            code="CST_QUERY_BACKUP_FAILED",
            details={"file_path": str(target)},
        )

    try:
        compile(new_source, str(target), "exec")
    except Exception as e:
        return backup_uuid, ErrorResult(
            message=f"Replacement code is not valid Python: {e}",
            code="CST_QUERY_INVALID_REPLACEMENT_CODE",
            details={"file_path": str(target), "backup_uuid": backup_uuid},
        )

    tmp_path = Path(str(target) + ".tmp")
    db_error: Optional[str] = None
    database = None
    try:
        tmp_path.write_text(new_source, encoding="utf-8")
        os.replace(str(tmp_path), str(target))

        saved_source = target.read_text(encoding="utf-8")
        if saved_source != new_source:
            raise RuntimeError("Post-write verification failed: file content mismatch")

        database = command._open_database_from_config(auto_analyze=False)
        abs_path = str(target.resolve())
        update_result = database.index_file(
            file_path=abs_path,
            project_id=project_id,
        )
        if not (isinstance(update_result, dict) and update_result.get("success")):
            db_error = (
                update_result.get("error")
                if isinstance(update_result, dict)
                else "index_file returned non-dict result"
            )
            raise RuntimeError(f"Database index failed: {db_error}")
        return backup_uuid, None
    except Exception as e:
        if db_error is None:
            db_error = str(e)
        try:
            rel_path = str(target.relative_to(root_path))
        except ValueError:
            rel_path = str(target)
        restore_success, restore_message = backup_manager.restore_file(rel_path, backup_uuid)
        if not restore_success:
            return backup_uuid, ErrorResult(
                message=(
                    "query_cst replace failed and rollback failed: "
                    f"{e}; restore error: {restore_message}"
                ),
                code="CST_QUERY_ROLLBACK_FAILED",
                details={
                    "file_path": str(target),
                    "backup_uuid": backup_uuid,
                    "db_error": db_error,
                },
            )
        return backup_uuid, ErrorResult(
            message=f"query_cst replace failed; file rolled back from backup: {e}",
            code="CST_QUERY_ERROR",
            details={
                "file_path": str(target),
                "backup_uuid": backup_uuid,
                "db_error": db_error,
            },
        )
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to delete temporary file: %s", tmp_path)
        if database is not None:
            database.disconnect()


def resolve_target_file(
    command: Any, project_id: str, file_path: str
) -> Union[Tuple[Path, Path], ErrorResult]:
    """Resolve project root and target file; return (root_path, target) or ErrorResult."""
    root_path = command._resolve_project_root(project_id)
    target = (root_path / file_path).resolve()
    if target.suffix != ".py":
        return ErrorResult(
            message="Target file must be a .py file",
            code="INVALID_FILE",
            details={"file_path": str(target)},
        )
    if not target.exists():
        return ErrorResult(
            message="Target file does not exist",
            code="FILE_NOT_FOUND",
            details={"file_path": str(target)},
        )
    return (root_path, target)


def validate_query_mode(
    is_replace_mode: bool,
    selector: Optional[str],
    range_only: bool,
    start_line: Optional[int],
    end_line: Optional[int],
    file_lines: int,
    use_replacements_list: bool,
) -> Optional[ErrorResult]:
    """Validate selector/range for query or replace mode; return ErrorResult if invalid."""
    if not is_replace_mode:
        if not selector:
            return ErrorResult(
                message="selector is required for query-only mode",
                code="CST_QUERY_MISSING_SELECTOR",
                details={},
            )
        return None
    if not range_only and not selector:
        return ErrorResult(
            message=(
                "For replace mode either selector or both start_line and end_line are required"
            ),
            code="CST_QUERY_MISSING_SELECTOR_OR_RANGE",
            details={},
        )
    if not range_only:
        return None
    assert start_line is not None and end_line is not None
    if start_line > end_line:
        return ErrorResult(
            message="start_line must be <= end_line",
            code="CST_QUERY_INVALID_RANGE",
            details={"start_line": start_line, "end_line": end_line},
        )
    if start_line < 1 or end_line > file_lines:
        return ErrorResult(
            message=(
                f"Line range [{start_line}, {end_line}] is out of file bounds (1..{file_lines})"
            ),
            code="CST_QUERY_INVALID_RANGE",
            details={
                "start_line": start_line,
                "end_line": end_line,
                "file_lines": file_lines,
            },
        )
    if use_replacements_list:
        return ErrorResult(
            message="replacements list is not supported with range-only replace; use replace_with or code_lines",
            code="CST_QUERY_RANGE_REPLACEMENTS_NOT_SUPPORTED",
            details={},
        )
    return None


def validate_replacements(
    replacements: List[Dict[str, Any]],
    match_count: int,
    selector: str,
) -> Optional[ErrorResult]:
    """Validate replacements list; return ErrorResult if invalid."""
    seen: set[int] = set()
    for i, entry in enumerate(replacements):
        idx = entry.get("match_index")
        if not isinstance(idx, int):
            return ErrorResult(
                message="replacements[].match_index must be an integer",
                code="CST_QUERY_REPLACEMENTS_INVALID",
                details={"entry_index": i},
            )
        if idx < 0 or idx >= match_count:
            return ErrorResult(
                message=(
                    f"match_index {idx} out of range "
                    f"(selector matched {match_count} node(s))"
                ),
                code="CST_QUERY_MATCH_INDEX",
                details={
                    "selector": selector,
                    "match_index": idx,
                    "match_count": match_count,
                },
            )
        if idx in seen:
            return ErrorResult(
                message=f"Duplicate match_index {idx} in replacements",
                code="CST_QUERY_REPLACEMENTS_DUPLICATE_INDEX",
                details={"match_index": idx},
            )
        seen.add(idx)
        has_replace_with = "replace_with" in entry and entry["replace_with"] is not None
        has_code_lines = "code_lines" in entry and entry["code_lines"] is not None
        if has_replace_with and has_code_lines:
            return ErrorResult(
                message=(
                    "replacements entry must have either replace_with or "
                    "code_lines, not both"
                ),
                code="CST_QUERY_REPLACEMENTS_BOTH_CODE",
                details={"entry_index": i, "match_index": idx},
            )
        if not has_replace_with and not has_code_lines:
            return ErrorResult(
                message=("replacements entry must have replace_with or code_lines"),
                code="CST_QUERY_REPLACEMENTS_MISSING_CODE",
                details={"entry_index": i, "match_index": idx},
            )
    return None


def build_ops_from_replacements(
    selector: str,
    replacements: List[Dict[str, Any]],
) -> Tuple[List[ReplaceOp], Dict[int, str]]:
    """Build ReplaceOp list and map match_index -> new_code for response."""
    ops: List[ReplaceOp] = []
    new_code_by_index: Dict[int, str] = {}
    for entry in replacements:
        idx = entry["match_index"]
        if "code_lines" in entry and entry["code_lines"] is not None:
            new_code = "\n".join(entry["code_lines"])
        else:
            new_code = entry.get("replace_with") or ""
        new_code_by_index[idx] = new_code
        ops.append(
            ReplaceOp(
                Selector(
                    kind="cst_query",
                    query=selector,
                    match_index=idx,
                ),
                new_code,
            )
        )
    return ops, new_code_by_index


def build_modified_nodes(
    matches: List[Any],
    replace_all: bool,
    match_index: int,
    single_new_code: Optional[str],
    new_code_by_index: Optional[Dict[int, str]],
) -> List[Dict[str, Any]]:
    """Build modified_nodes list for replace response."""
    modified_nodes = []
    if new_code_by_index is not None:
        for idx, code in new_code_by_index.items():
            m = matches[idx]
            modified_nodes.append(
                {
                    "node_id": m.node_id,
                    "kind": m.kind,
                    "start_line": m.start_line,
                    "end_line": m.end_line,
                    "code": code,
                }
            )
    elif replace_all and single_new_code is not None:
        for m in matches:
            modified_nodes.append(
                {
                    "node_id": m.node_id,
                    "kind": m.kind,
                    "start_line": m.start_line,
                    "end_line": m.end_line,
                    "code": single_new_code,
                }
            )
    elif single_new_code is not None:
        m = matches[match_index]
        modified_nodes.append(
            {
                "node_id": m.node_id,
                "kind": m.kind,
                "start_line": m.start_line,
                "end_line": m.end_line,
                "code": single_new_code,
            }
        )
    return modified_nodes


def run_replace_flow(
    command: Any,
    root_path: Path,
    target: Path,
    source: str,
    ops: List[ReplaceOp],
    file_path: str,
    project_id: str,
    preview_mode: bool,
    selector_for_query: str,
    t_start: float,
    matches: List[Any],
    range_only: bool,
    replace_all: bool,
    match_index: int,
    single_new_code: Optional[str],
    new_code_by_index: Optional[Dict[int, str]],
) -> Union[SuccessResult, ErrorResult]:
    """
    Apply replace ops: apply_replace_ops, then preview or backup/write/index.
    Returns SuccessResult with replace_data.
    """
    try:
        new_source, stats = apply_replace_ops(source, ops)
    except CSTModulePatchError as e:
        return ErrorResult(
            message=str(e),
            code="CST_REPLACE_ERROR",
            details={"selector": selector_for_query},
        )

    if preview_mode:
        diff = unified_diff(source, new_source, file_path)
        replace_data = {
            "success": True,
            "preview": True,
            "replaced": stats.get("replaced", 0),
            "removed": stats.get("removed", 0),
            "file_path": str(target),
            "diff": diff,
            "modified_source": new_source,
            "file_size_bytes": len(new_source.encode("utf-8")),
            "file_lines": len(new_source.splitlines()),
        }
        logger.info(
            "[TIMING] command=query_cst total_elapsed_sec=%.4f (preview)",
            time.perf_counter() - t_start,
        )
        return SuccessResult(data=replace_data)

    backup_uuid, write_error = _write_replace_result_atomically(
        command=command,
        root_path=root_path,
        target=target,
        new_source=new_source,
        project_id=project_id,
    )
    if write_error is not None:
        return write_error
    logger.info(
        "[TIMING] command=query_cst total_elapsed_sec=%.4f",
        time.perf_counter() - t_start,
    )
    if range_only or not matches:
        modified_nodes = []
    else:
        modified_nodes = build_modified_nodes(
            matches,
            replace_all=replace_all,
            match_index=match_index,
            single_new_code=single_new_code,
            new_code_by_index=new_code_by_index,
        )
    replace_data = {
        "success": True,
        "replaced": stats.get("replaced", 0),
        "removed": stats.get("removed", 0),
        "file_path": str(target),
        "backup_uuid": backup_uuid or None,
        "file_size_bytes": len(new_source.encode("utf-8")),
        "file_lines": len(new_source.splitlines()),
        "modified_nodes": modified_nodes,
    }
    return SuccessResult(data=replace_data)
