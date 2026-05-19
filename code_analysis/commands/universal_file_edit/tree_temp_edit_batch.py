"""Apply universal_file_edit operations to TreeNode-backed tree-temp sessions (G-003 / G-004).

Author: Vasiliy Zdanovskiy
Email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, cast

import yaml
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.universal_file_edit.errors import (
    PARSE_ERROR,
    UNKNOWN_FORMAT,
    WRITE_FAILED,
    error_result_for_edit,
    error_result_from_make_error,
    make_error,
)
from code_analysis.commands.universal_file_edit.format_group import FORMAT_TREE_TEMP
from code_analysis.commands.universal_file_edit.session import EditSession
from code_analysis.commands.universal_file_edit.tree_temp_edit_nodes import (
    apply_single_tree_temp_mutation,
    serialize_tree_temp_roots,
)
from code_analysis.core.backup_manager import BackupManager
from code_analysis.core.json_tree.tree_builder import get_tree as json_get_registered
from code_analysis.core.json_tree.tree_modifier import modify_tree as json_modify_tree
from code_analysis.core.yaml_tree.tree_builder import get_tree as yaml_get_tree


def _project_root_near(path: Path) -> Path:
    """Locate project-like root upward from ``path`` for backups."""
    resolved = path.resolve()
    probe = resolved.parent if resolved.is_file() else resolved
    for candidate in (probe,) + tuple(probe.parents):
        if (candidate / "pyproject.toml").exists() or (
            candidate / "projectid"
        ).exists():
            return candidate
    raise ValueError(f"Cannot resolve project root near {resolved}")


def _normalized_json_modify_operation(op: Dict[str, Any]) -> Dict[str, Any]:
    """Map universal-edit op keys into ``core.json_tree.tree_modifier`` shape."""
    m = dict(op)
    if "json_pointer" not in m and "node_ref" in m:
        ref = m.get("node_ref")
        if ref == "" or (isinstance(ref, str) and ref.startswith("/")):
            m["json_pointer"] = ref
    for ref_key, id_key in (
        ("node_ref", "node_id"),
        ("parent_node_ref", "parent_node_id"),
        ("target_node_ref", "target_node_id"),
    ):
        if ref_key in m and not m.get(id_key):
            m[id_key] = m[ref_key]
    raw_action = op.get("action")
    raw_type = op.get("type")
    if isinstance(raw_action, str) and raw_action.strip():
        m["action"] = raw_action.strip().lower()
    elif isinstance(raw_type, str) and raw_type.strip():
        m["action"] = raw_type.strip().lower()
    if "value" not in m and "content" in m:
        cnt = m.get("content")
        if isinstance(cnt, str):
            try:
                m["value"] = json.loads(cnt)
            except json.JSONDecodeError:
                m["value"] = cnt
        else:
            m["value"] = cnt
    return m


def _modify_yaml_registered_one(tree_id: str, mop: Dict[str, Any]) -> None:
    """Apply one JSON-shaped modify dict to YAML tree and rebuild its index."""

    from code_analysis.core.json_tree.models import JSONTree
    from code_analysis.core.json_tree.tree_modifier import (
        _op_delete,
        _op_insert,
        _op_replace,
    )
    from code_analysis.core.yaml_tree.tree_builder import (
        _build_index as yaml_rebuild_index,
        get_tree as yaml_get_registered_inner,
    )

    tree = yaml_get_registered_inner(tree_id)
    if tree is None:
        raise ValueError(f"YAML tree not found: {tree_id}")
    act = str(mop.get("action") or "").lower()
    jtree = cast(JSONTree, tree)
    if act == "replace":
        _op_replace(jtree, mop)
    elif act == "delete":
        _op_delete(jtree, mop)
    elif act == "insert":
        _op_insert(jtree, mop)
    else:
        raise ValueError(f"Unknown YAML tree action: {act!r}")
    yaml_rebuild_index(tree)


def _run_legacy_tree_temp_apply(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    tid = session.tree_id
    if not tid:
        return error_result_for_edit(
            "Session has no registered tree id for tree-temp format.",
            "INVALID_SESSION",
            None,
        )
    try:
        root_dir = _project_root_near(session.draft_path)
        bm = BackupManager(root_dir=root_dir)
        if session.draft_path.exists():
            bm.create_backup(
                session.draft_path,
                command="universal_file_edit",
            )
    except Exception as exc:
        return error_result_for_edit(
            f"Backup before edit failed: {exc}",
            WRITE_FAILED,
            {"path": str(session.draft_path)},
        )

    try:
        if session.handler_id == "json":
            for op in operations:
                mop = _normalized_json_modify_operation(op)
                json_modify_tree(tid, [mop])
                jt = json_get_registered(tid)
                if jt is None:
                    return error_result_for_edit(
                        f"JSON tree not found after apply: {tid}",
                        PARSE_ERROR,
                        None,
                    )
                dump = json.dumps(jt.root_data, indent=2, ensure_ascii=False) + "\n"
                session.draft_path.write_text(
                    dump,
                    encoding="utf-8",
                )
        elif session.handler_id == "yaml":
            for op in operations:
                mop = _normalized_json_modify_operation(op)
                _modify_yaml_registered_one(tid, mop)
                yt = yaml_get_tree(tid)
                if yt is None:
                    return error_result_for_edit(
                        f"YAML tree not found after apply: {tid}",
                        PARSE_ERROR,
                        None,
                    )
                session.draft_path.write_text(
                    yaml.safe_dump(
                        yt.root_data,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    ),
                    encoding="utf-8",
                )
        else:
            return error_result_from_make_error(
                cast(
                    Dict[str, Any],
                    make_error(
                        UNKNOWN_FORMAT,
                        f"Unsupported handler for tree-temp: {session.handler_id}",
                    ),
                )
            )
    except ValueError as exc:
        return error_result_for_edit(
            str(exc),
            "INVALID_OPERATION",
            {"operations": operations},
        )

    return SuccessResult(data={"success": True, "updated": True})


def apply_tree_temp_mutations(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    if session.format_group != FORMAT_TREE_TEMP:
        return error_result_for_edit(
            "Session format_group is not tree-temp.",
            "INVALID_SESSION",
            None,
        )
    if session.tree_temp_roots is None:
        return _run_legacy_tree_temp_apply(session, operations)

    roots_snap = deepcopy(session.tree_temp_roots)

    try:
        root_dir = _project_root_near(session.draft_path)
        bm = BackupManager(root_dir=root_dir)
        if session.draft_path.exists():
            bm.create_backup(
                session.draft_path,
                command="universal_file_edit",
            )
    except Exception as exc:
        return error_result_for_edit(
            f"Backup before edit failed: {exc}",
            WRITE_FAILED,
            {"path": str(session.draft_path)},
        )

    roots = session.tree_temp_roots

    def rollback() -> None:
        session.tree_temp_roots = deepcopy(roots_snap)
        session.draft_path.write_text(
            serialize_tree_temp_roots(session.handler_id, session.tree_temp_roots),
            encoding="utf-8",
        )

    try:
        for op in operations:
            mop = _normalized_json_modify_operation(op)
            try:
                apply_single_tree_temp_mutation(roots, session.handler_id, mop)
            except ValueError as exc:
                rollback()
                return error_result_for_edit(
                    str(exc),
                    "INVALID_OPERATION",
                    {"operations": operations},
                )
        session.draft_path.write_text(
            serialize_tree_temp_roots(session.handler_id, roots),
            encoding="utf-8",
        )
        session.dirty = True
        return SuccessResult(data={"success": True, "updated": True})
    except ValueError as exc:
        rollback()
        return error_result_for_edit(
            str(exc),
            "INVALID_OPERATION",
            {"operations": operations},
        )
