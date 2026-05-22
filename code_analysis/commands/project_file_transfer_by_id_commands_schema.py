"""
JSON-schema-like input schemas for project file transfer-by-id MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict


def get_project_file_transfer_download_begin_schema() -> Dict[str, Any]:
    """Machine-readable schema for ``project_file_transfer_download_begin``."""
    return {
        "type": "object",
        "description": (
            "Begin a resumable download of an indexed project file (read-only). "
            "Pass ``file_id`` (``files`` primary key UUID). The server resolves project "
            "and path from the row. Optional ``project_id`` scopes the lookup to that "
            "project. ``file_path`` is not accepted — use ``file_id`` from "
            "``list_project_files``. Client façade: ``FileSessionClient.download``; "
            "boolean ``lock`` maps to ``lock_mode`` (``true`` → ``full``, ``false`` → "
            "``none``)."
        ),
        "properties": {
            "file_id": {
                "type": "string",
                "description": (
                    "Primary key of the row in table ``files`` (UUID string). Required. "
                    "Project and path are resolved from this row."
                ),
            },
            "project_id": {
                "type": "string",
                "description": (
                    "Optional project UUID from ``list_projects``. When provided, the "
                    "``files`` row must belong to this project."
                ),
            },
            "compression": {
                "type": "string",
                "enum": ["identity", "gzip"],
                "description": (
                    "Wire representation for chunk stream: ``identity`` serves raw bytes; "
                    "``gzip`` serves gzip-compressed wire bytes. Plaintext checksum in the "
                    "receipt still refers to the uncompressed file (same as "
                    "``transfer_download_begin``)."
                ),
            },
            "chunk_size": {
                "type": "integer",
                "description": (
                    "Optional suggested maximum bytes per chunk read; the server may clamp to "
                    "its configured maximum."
                ),
            },
            "include_backup_history": {
                "type": "boolean",
                "default": True,
                "description": (
                    "When true (default), the success payload includes ``backup_history``: "
                    "entries from the project ``old_code`` index for this project-relative path "
                    "(same as BackupManager.list_versions). When false, omit that list."
                ),
            },
            "session_id": {
                "type": "string",
                "description": (
                    "Client session UUID from ``session_create``. When set, the session must "
                    "exist in ``client_sessions`` (``SESSION_NOT_FOUND`` otherwise). Required "
                    "when ``lock_mode`` is not ``none``. Also records ``session_file_locks`` "
                    "when the target file is indexed."
                ),
            },
            "lock_mode": {
                "type": "string",
                "enum": ["none", "block_write", "full"],
                "default": "none",
                "description": (
                    "Advisory transfer lock for cooperative editing. ``none`` — read without "
                    "locking (client ``lock=false``). ``full`` — exclusive sidecar flock until "
                    "download completes (client ``lock=true``). ``block_write`` — shared flock "
                    "(advanced). Non-none locks require ``session_id``."
                ),
            },
            "job_id": {
                "type": "string",
                "description": (
                    "Optional queue job identifier stored on the transfer session for adapter "
                    "correlation (e.g. WebSocket artifact_ready)."
                ),
            },
            "correlation_id": {
                "type": "string",
                "description": "Optional opaque client correlation id stored on the session.",
            },
        },
        "required": ["file_id", "compression"],
        "additionalProperties": False,
    }


def get_project_file_transfer_upload_save_schema() -> Dict[str, Any]:
    """Machine-readable schema for ``project_file_transfer_upload_save``."""
    return {
        "type": "object",
        "description": (
            "Apply the body of a completed adapter upload to a project file. Two selector "
            "modes — **exactly one**:\n\n"
            "1. **Update existing** — ``file_id`` only. ``project_id`` and ``file_path`` "
            "are omitted; the ``files`` row determines project and path. Optional "
            "``project_id`` must match the row if provided.\n\n"
            "2. **Create new** — ``project_id`` + ``file_path`` (literal path relative to "
            "project root). The path must **not** already be indexed in ``files`` "
            "(``FILE_ALREADY_INDEXED`` otherwise).\n\n"
            "Client façade: ``FileSessionClient.upload`` (mode 1) and ``.upload_new`` "
            "(mode 2). Boolean ``unlock`` maps to ``unlock_after_write`` (default ``true``)."
        ),
        "properties": {
            "project_id": {
                "type": "string",
                "description": (
                    "Project UUID from ``list_projects``. **Required** in new-file mode "
                    "(with ``file_path``, ``file_id`` omitted). **Omit** in id-only update "
                    "mode when ``file_id`` is set; if provided anyway, the ``files`` row must "
                    "belong to this project."
                ),
            },
            "file_id": {
                "type": "string",
                "description": (
                    "Target ``files`` row UUID. **Update mode:** pass this alone to overwrite "
                    "an existing indexed file. Mutually exclusive with ``file_path``."
                ),
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Target path relative to project root (literal; no globs). **New-file mode:** "
                    "required together with ``project_id`` when ``file_id`` is omitted. The path "
                    "must not already have a row in ``files`` — use ``file_id`` to update an "
                    "existing indexed file. Mutually exclusive with ``file_id``."
                ),
            },
            "transfer_id": {
                "type": "string",
                "description": (
                    "Upload session id returned by ``transfer_upload_complete`` after all "
                    "chunks were uploaded. Must reference a completed upload session."
                ),
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": (
                    "When true, validate only: no write, no backup, no DB side effects from "
                    "the save handler. When false, perform full save like ``universal_file_save``."
                ),
            },
            "diff": {
                "type": "boolean",
                "default": False,
                "description": (
                    "When true, include a unified diff in the response when the selected handler "
                    "supports it."
                ),
            },
            "backup": {
                "type": "boolean",
                "default": True,
                "description": (
                    "When true (default), enable backups where the handler does (e.g. Python, "
                    "JSON, YAML; text handler uses BackupManager separately). Set false only "
                    "with care; breaks parity with local ``universal_file_save`` versioning."
                ),
            },
            "commit_message": {
                "type": "string",
                "description": (
                    "Optional non-empty git commit message; passed through to the same "
                    "post-write git hook as ``universal_file_save`` when configured."
                ),
            },
            "diff_context_lines": {
                "type": "integer",
                "description": (
                    "Optional number of context lines for unified diff when ``diff`` is true."
                ),
            },
            "validate_syntax_only": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Python handler only: when true, validate syntax (e.g. ast.parse) without "
                    "full checks where the handler supports this flag."
                ),
            },
            "tree_id": {
                "type": "string",
                "description": (
                    "Optional CST ``tree_id`` for Python saves when the handler accepts an "
                    "in-memory tree (same semantics as ``universal_file_save``)."
                ),
            },
            "session_id": {
                "type": "string",
                "description": (
                    "Client session UUID from ``session_create``. When set, must exist in "
                    "``client_sessions``. Used for lock attribution and ``unlock_after_write`` "
                    "(client ``unlock``) cleanup. Required when ``lock_mode`` is not ``none``."
                ),
            },
            "unlock_after_write": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Release runtime transfer and ``session_file_locks`` after a successful "
                    "non-dry-run save. Client façade ``unlock=true`` (default). Set ``false`` "
                    "when the caller will release locks manually."
                ),
            },
            "lock_mode": {
                "type": "string",
                "enum": ["none", "block_write", "full"],
                "default": "none",
                "description": (
                    "Optional advisory lock acquired around the save when no prior transfer "
                    "lock was taken. ``block_write`` is shared; ``full`` is exclusive. With "
                    "``session_id``, the lock is attributed to that client session."
                ),
            },
        },
        "required": ["transfer_id"],
        "additionalProperties": False,
    }
