"""
Build aggregated session view: locked files by project and subordinate sessions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Optional

from code_analysis.main_server_presentation import resolve_server_presentation

if TYPE_CHECKING:
    from code_analysis.core.database_client.client import DatabaseClient


def _project_relative_path(file_row: Mapping[str, Any]) -> str:
    rel = str(file_row.get("relative_path") or "").strip()
    if rel:
        return rel.replace("\\", "/")
    path = str(file_row.get("file_path") or file_row.get("path") or "").strip()
    return path.replace("\\", "/")


def format_project_presentation(
    *,
    project_id: str,
    project_name: Optional[str],
    project_comment: Optional[str],
    root_path: Optional[str] = None,
) -> str:
    """Human-readable project label for session view."""
    name = str(project_name or "").strip()
    comment = str(project_comment or "").strip()
    if name and comment:
        return f"{name} — {comment}"
    if name:
        return name
    if comment:
        return comment
    if root_path:
        return str(root_path)
    return project_id


def format_session_presentation(
    comment: Optional[str], session_id: str
) -> Optional[str]:
    """Human-readable session label; None when session row is missing."""
    text = str(comment or "").strip()
    return text or None


def resolve_server_presentation_for_uuid(
    server_uuid: str,
    *,
    current_server_uuid: str,
    app_config: Mapping[str, Any],
) -> Optional[dict[str, str]]:
    """
    Return server presentation when ``server_uuid`` matches this server instance.

    Other server UUIDs are unknown to the local config — returns None.
    """
    if not server_uuid or not current_server_uuid:
        return None
    if str(server_uuid).strip() != str(current_server_uuid).strip():
        return None
    title, description, version = resolve_server_presentation(dict(app_config))
    return {
        "title": title,
        "description": description,
        "version": version,
    }


def build_session_view(
    database: DatabaseClient,
    session_id: str,
    *,
    app_config: Mapping[str, Any],
) -> dict[str, object]:
    """
    Build session view payload for one client session.

    Returns:
        dict with session_id, locked_files_by_project, subordinate_sessions.
    """
    current_server_uuid = str(
        (app_config.get("registration") or {}).get("instance_uuid") or ""
    )

    lock_rows = database.execute(
        "SELECT sfl.project_id, sfl.file_id, sfl.locked_at, "
        "f.relative_path, f.path AS file_path, "
        "p.name AS project_name, p.comment AS project_comment, p.root_path "
        "FROM session_file_locks sfl "
        "LEFT JOIN files f ON f.id = sfl.file_id AND f.project_id = sfl.project_id "
        "LEFT JOIN projects p ON p.id = sfl.project_id "
        "WHERE sfl.session_id = ? "
        "ORDER BY sfl.project_id ASC, sfl.locked_at ASC",
        (session_id,),
    )
    locks = lock_rows.get("data") or []

    by_project: dict[str, dict[str, object]] = {}
    for row in locks:
        row_dict = dict(row)
        project_id = str(row_dict["project_id"])
        bucket = by_project.get(project_id)
        if bucket is None:
            bucket = {
                "project_id": project_id,
                "project_presentation": format_project_presentation(
                    project_id=project_id,
                    project_name=row_dict.get("project_name"),
                    project_comment=row_dict.get("project_comment"),
                    root_path=row_dict.get("root_path"),
                ),
                "files": [],
            }
            by_project[project_id] = bucket
        files_list = bucket["files"]
        assert isinstance(files_list, list)
        files_list.append(
            {
                "file_id": str(row_dict["file_id"]),
                "file_path": _project_relative_path(row_dict),
                "locked_at": row_dict.get("locked_at"),
            }
        )

    sub_rows = database.execute(
        "SELECT ss.server_uuid, ss.comment AS link_comment, "
        "cs.comment AS leading_comment "
        "FROM subordinate_sessions ss "
        "LEFT JOIN client_sessions cs ON cs.session_id = ss.parent_session_id "
        "WHERE ss.parent_session_id = ? "
        "ORDER BY ss.server_uuid ASC",
        (session_id,),
    )
    subordinate_sessions: list[dict[str, object]] = []
    for row in sub_rows.get("data") or []:
        row_dict = dict(row)
        server_uuid = str(row_dict["server_uuid"])
        subordinate_sessions.append(
            {
                "session_id": session_id,
                "server_uuid": server_uuid,
                "session_presentation": format_session_presentation(
                    row_dict.get("leading_comment"), session_id
                ),
                "server_presentation": resolve_server_presentation_for_uuid(
                    server_uuid,
                    current_server_uuid=current_server_uuid,
                    app_config=app_config,
                ),
                "link_comment": str(row_dict.get("link_comment") or ""),
            }
        )

    locked_files_by_project = list(by_project.values())
    return {
        "session_id": session_id,
        "locked_files_by_project": locked_files_by_project,
        "locked_file_count": len(locks),
        "subordinate_sessions": subordinate_sessions,
        "subordinate_session_count": len(subordinate_sessions),
    }
