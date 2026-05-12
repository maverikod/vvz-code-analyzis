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
            "Begin a resumable download of the current on-disk project file. "
            "Provide **exactly one** of ``file_id`` (``files`` primary key) or ``file_path`` "
            "(literal path relative to project root). When ``file_id`` is omitted, "
            "``project_id`` and ``file_path`` are both required. When ``file_id`` is set, "
            "``project_id`` and ``file_path`` are optional (optional ``project_id`` scopes the "
            "lookup to that project). Verifies the file exists under the project root, then "
            "creates the same download session as ``transfer_download_begin`` (chunked GET). "
            "Does not modify disk or DB."
        ),
        "properties": {
            "project_id": {
                "type": "string",
                "description": (
                    "Project UUID from list_projects. **Required** when ``file_id`` is omitted "
                    "(path mode with ``file_path``). **Optional** when ``file_id`` is set; if "
                    "provided, the file row must belong to this project."
                ),
            },
            "file_id": {
                "type": "string",
                "description": (
                    "Primary key of the row in table ``files`` (UUID string). Mutually exclusive "
                    "with ``file_path``. When set, ``project_id`` and ``file_path`` are optional."
                ),
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Literal project-relative file path (POSIX ``/``). No wildcards. "
                    "**Required** when ``file_id`` is omitted (together with ``project_id``). "
                    "The file must exist on disk under the project root. Mutually exclusive "
                    "with ``file_id``. When the path is indexed, the response includes the same "
                    "``file_id`` as ``list_project_files``; otherwise ``file_id`` in the response "
                    "is null."
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
            "lock_mode": {
                "type": "string",
                "enum": ["none", "block_write", "full"],
                "default": "none",
                "description": (
                    "Optional advisory transfer lock. ``none`` preserves legacy behavior. "
                    "``block_write`` takes a shared sidecar flock so cooperative writers block. "
                    "``full`` takes an exclusive sidecar flock. Non-none locks are held until "
                    "the adapter reports the download completed (or transfer ack/expiry/error "
                    "cleanup releases them)."
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
        "required": ["compression"],
        "additionalProperties": False,
    }


def get_project_file_transfer_upload_save_schema() -> Dict[str, Any]:
    """Machine-readable schema for ``project_file_transfer_upload_save``."""
    return {
        "type": "object",
        "description": (
            "Apply the body of a completed adapter upload (``transfer_upload_complete``) to "
            "a project file. Provide **exactly one** of ``file_id`` or ``file_path``. "
            "When ``file_id`` is omitted, ``project_id`` and ``file_path`` are both required. "
            "When ``file_id`` is set, ``project_id`` and ``file_path`` are optional. Uses the "
            "same registry-first save pipeline as ``universal_file_save``. Safe preview via "
            "``dry_run=true``."
        ),
        "properties": {
            "project_id": {
                "type": "string",
                "description": (
                    "Project UUID from list_projects. **Required** when ``file_id`` is omitted. "
                    "**Optional** when ``file_id`` is set; if provided, the file row must belong "
                    "to this project."
                ),
            },
            "file_id": {
                "type": "string",
                "description": (
                    "Target ``files`` row UUID; path comes from that row. Mutually exclusive "
                    "with ``file_path``. When set, ``project_id`` and ``file_path`` are optional."
                ),
            },
            "file_path": {
                "type": "string",
                "description": (
                    "Target path relative to project root (literal; no globs). **Required** when "
                    "``file_id`` is omitted (with ``project_id``). Mutually exclusive with "
                    "``file_id``. The file may exist already or be created by the handler per "
                    "``universal_file_save`` rules."
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
            "unlock_after_write": {
                "type": "boolean",
                "default": True,
                "description": (
                    "When true (default), release any runtime transfer lock for this "
                    "transfer/file after a successful non-dry-run save."
                ),
            },
            "lock_mode": {
                "type": "string",
                "enum": ["none", "block_write", "full"],
                "default": "none",
                "description": (
                    "Optional advisory lock acquired around the save when no prior transfer "
                    "lock was taken. ``block_write`` is shared; ``full`` is exclusive."
                ),
            },
        },
        "required": ["transfer_id"],
        "additionalProperties": False,
    }
