"""
Canonical command names for the high-level client API vs the live server registry.

**code-analysis-server** owns project trees, the index database, sessions, locks,
and editor ingress (chunked transfer). It does **not** expose in-server content
editing (``universal_file_open/edit/write/close``, CST/JSON tree modify/save,
``format_code``, legacy line writers).

**File content on CA** — read-only surface only:

- :data:`FILE_CONTENT_READ_COMMANDS` — preview and search (including on-disk
  grep for files not yet indexed).
- :data:`FS_COMMANDS` — filesystem operations (copy/move/remove/list/grep); not
  the structured edit workflow.

Editor clients use :data:`CLIENT_FACADE_COMMANDS` (sessions, transfer, locks,
``universal_file_preview`` / ``universal_file_search``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Callable, Dict, FrozenSet, Tuple

# Removed from the public server surface — do not use in client facades or docs.
LEGACY_REMOVED_COMMANDS: FrozenSet[str] = frozenset(
    {
        "universal_file_read",
        "universal_file_save",
        "universal_file_replace",
        "universal_file_delete",
        "read_project_text_file",
        "write_project_text_lines",
        "create_text_file",
        "replace_file_lines",
    }
)

# CST / JSON tree MCP workflow — modules may exist in the repo but are not registered.
CST_REMOVED_COMMANDS: FrozenSet[str] = frozenset(
    {
        "cst_load_file",
        "cst_save_tree",
        "cst_modify_tree",
        "cst_create_file",
        "cst_find_node",
        "cst_get_node_info",
        "cst_get_node_by_range",
        "cst_get_node_at_line",
        "cst_reload_tree",
        "cst_convert_and_save",
        "cst_apply_buffer",
        "cst_list_trees",
        "cst_unload_tree",
        "list_cst_blocks",
        "query_cst",
        "json_load_file",
        "json_find_node",
        "json_get_node_info",
        "json_modify_tree",
        "json_save_tree",
        "json_reload_tree",
    }
)

# Content editing on ai-editor-server only (not on code-analysis-server).
EDITING_REMOVED_COMMANDS: FrozenSet[str] = frozenset(
    {
        "universal_file_open",
        "universal_file_edit",
        "universal_file_write",
        "universal_file_close",
        "universal_file_move_nodes",
        "session_git_log",
        "session_git_diff",
        "session_git_show",
        "session_git_status",
        "session_git_revert",
        "session_undo",
        "session_redo",
        "session_write",
        "delete_file",
        "delete_files_by_mask",
        "restore_deleted_files",
        "unmark_deleted_file",
        "cleanup_deleted_files",
        "collapse_versions",
        "restore_backup_file",
        "delete_backup",
        "clear_all_backups",
        "split_class",
        "extract_superclass",
        "split_file_to_package",
        "format_code",
    }
)

REMOVED_COMMANDS: FrozenSet[str] = (
    LEGACY_REMOVED_COMMANDS | CST_REMOVED_COMMANDS | EDITING_REMOVED_COMMANDS
)

# Read-only file **content** on CA (no mutate/edit workflow). Includes on-disk search
# (``fs_grep``, paginated ``search_*``) for paths not yet in the index.
FILE_CONTENT_READ_COMMANDS: FrozenSet[str] = frozenset(
    {
        "universal_file_preview",
        "universal_file_search",
        "get_file_lines",
        "fs_grep",
        "search_start",
        "search_get_page",
        "search_get_status",
        "search_cancel",
        "search_close",
    }
)

# Filesystem helpers — separate from structured content editing; may touch paths/bytes
# via copy/move/remove but are not universal_file_edit / CST / format_code.
FS_COMMANDS: FrozenSet[str] = frozenset(
    {
        "fs_copy",
        "fs_move",
        "fs_remove",
        "fs_list_projects",
    }
)

# Client sessions + DB file locks — persisted on this server for editor/terminal clients.
FILE_SESSION_COMMANDS: FrozenSet[str] = frozenset(
    {
        "session_create",
        "session_validate",
        "session_delete",
        "session_list",
        "session_view",
        "session_open_file",
        "session_close_file",
        "session_list_file_locks",
        "subordinate_session_create",
        "subordinate_session_get",
        "subordinate_session_update",
        "subordinate_session_delete",
        "subordinate_session_list",
    }
)

TRANSFER_AND_LOCK_COMMANDS: FrozenSet[str] = frozenset(
    {
        "project_file_transfer_download_begin",
        "project_file_transfer_upload_save",
        "project_file_advisory_lock_batch",
    }
)

UNIVERSAL_FILE_COMMANDS: FrozenSet[str] = frozenset(
    {
        "universal_file_preview",
        "universal_file_search",
    }
)

CLIENT_FACADE_COMMANDS: FrozenSet[str] = (
    FILE_SESSION_COMMANDS | TRANSFER_AND_LOCK_COMMANDS | UNIVERSAL_FILE_COMMANDS
)

# ``FileSessionClient`` method names for each ``FILE_SESSION_COMMANDS`` entry.
# ``session_list_file_locks`` is also used by ``assert_session_exists``.
FILE_SESSION_FACADE_METHODS: Dict[str, str] = {
    "session_create": "create_session",
    "session_validate": "validate_session",
    "session_delete": "delete_session",
    "session_list": "list_sessions",
    "session_view": "view_session",
    "session_open_file": "lock_file",
    "session_close_file": "unlock_file",
    "session_list_file_locks": "list_file_locks",
    "subordinate_session_create": "create_subordinate_session",
    "subordinate_session_get": "get_subordinate_session",
    "subordinate_session_update": "update_subordinate_session",
    "subordinate_session_delete": "delete_subordinate_session",
    "subordinate_session_list": "list_subordinate_sessions",
}

# Transfer / advisory-lock commands may map to more than one façade method.
TRANSFER_FACADE_METHODS: Dict[str, Tuple[str, ...]] = {
    "project_file_transfer_download_begin": ("download",),
    "project_file_transfer_upload_save": ("upload", "upload_new"),
    "project_file_advisory_lock_batch": (
        "lock_files_advisory",
        "unlock_files_advisory",
    ),
}


def assert_file_session_facade_complete() -> None:
    """Raise ``AssertionError`` if ``FILE_SESSION_FACADE_METHODS`` is incomplete."""
    missing_cmds = FILE_SESSION_COMMANDS - set(FILE_SESSION_FACADE_METHODS)
    extra_cmds = set(FILE_SESSION_FACADE_METHODS) - FILE_SESSION_COMMANDS
    if missing_cmds or extra_cmds:
        raise AssertionError(
            "FILE_SESSION_FACADE_METHODS out of sync with FILE_SESSION_COMMANDS: "
            f"missing={sorted(missing_cmds)!r} extra={sorted(extra_cmds)!r}"
        )
    from code_analysis_client.file_session import FileSessionClient

    for command, method_name in FILE_SESSION_FACADE_METHODS.items():
        if not hasattr(FileSessionClient, method_name):
            raise AssertionError(
                f"FileSessionClient missing method {method_name!r} for command {command!r}"
            )


def assert_transfer_facade_complete() -> None:
    """Raise ``AssertionError`` if ``TRANSFER_FACADE_METHODS`` is incomplete."""
    missing_cmds = TRANSFER_AND_LOCK_COMMANDS - set(TRANSFER_FACADE_METHODS)
    extra_cmds = set(TRANSFER_FACADE_METHODS) - TRANSFER_AND_LOCK_COMMANDS
    if missing_cmds or extra_cmds:
        raise AssertionError(
            "TRANSFER_FACADE_METHODS out of sync with TRANSFER_AND_LOCK_COMMANDS: "
            f"missing={sorted(missing_cmds)!r} extra={sorted(extra_cmds)!r}"
        )
    from code_analysis_client.file_session import FileSessionClient

    for command, method_names in TRANSFER_FACADE_METHODS.items():
        for method_name in method_names:
            if not hasattr(FileSessionClient, method_name):
                raise AssertionError(
                    f"FileSessionClient missing method {method_name!r} "
                    f"for command {command!r}"
                )


def _command_registered(get_command: Callable[[str], object], name: str) -> bool:
    try:
        get_command(name)
        return True
    except KeyError:
        return False


def assert_facade_commands_registered(get_command: Callable[[str], object]) -> None:
    """Raise ``KeyError`` if any facade command is missing from the server registry."""
    missing = [
        name
        for name in sorted(CLIENT_FACADE_COMMANDS)
        if not _command_registered(get_command, name)
    ]
    if missing:
        raise KeyError(f"Client facade commands not registered on server: {missing}")


def assert_removed_commands_absent(get_command: Callable[[str], object]) -> None:
    """Raise ``AssertionError`` if a removed command is still registered."""
    present = [
        name
        for name in sorted(REMOVED_COMMANDS)
        if _command_registered(get_command, name)
    ]
    if present:
        raise AssertionError(f"Removed commands still registered: {present}")


def assert_file_content_read_commands_registered(
    get_command: Callable[[str], object],
) -> None:
    """Raise ``KeyError`` if a read-only content command is missing from the registry."""
    missing = [
        name
        for name in sorted(FILE_CONTENT_READ_COMMANDS)
        if not _command_registered(get_command, name)
    ]
    if missing:
        raise KeyError(f"File content read commands not registered: {missing}")


def assert_fs_commands_registered(get_command: Callable[[str], object]) -> None:
    """Raise ``KeyError`` if a filesystem helper command is missing from the registry."""
    missing = [
        name
        for name in sorted(FS_COMMANDS)
        if not _command_registered(get_command, name)
    ]
    if missing:
        raise KeyError(f"Filesystem commands not registered: {missing}")
