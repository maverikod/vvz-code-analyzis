"""
Extended MCP metadata for project file transfer-by-id commands (AI/help).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Type


def get_project_file_transfer_download_begin_metadata(
    cls: Type[Any],
) -> Dict[str, Any]:
    """Documentation-oriented metadata for ``project_file_transfer_download_begin``."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "Maps an indexed project file to the mcp-proxy-adapter **download transfer** flow.\n\n"
            "Pass ``file_id`` (``files`` primary key). Project and path are resolved from the "
            "row. Optional ``project_id`` must match that row when provided. ``file_path`` is "
            "not accepted.\n\n"
            "**Client façade** (``code-analysis-client``): ``FileSessionClient.download``. "
            "Boolean ``lock`` maps to ``lock_mode``: ``true`` → ``full``, ``false`` → ``none``.\n\n"
            "After this command succeeds, clients read bytes using the returned "
            "``transport.chunk_path_template`` (GET with ``offset`` and ``limit``) and the same "
            "authentication as JSON-RPC, exactly as for the built-in transfer download command.\n\n"
            "**History / provenance:** When ``include_backup_history`` is true (default), the "
            "response includes ``backup_history``: prior snapshots listed in ``old_code`` for "
            "that project-relative path (timestamps, backup UUIDs, commands), matching what "
            "``BackupManager`` records for local saves.\n\n"
            "**Safety:** Read-only with respect to project files and DB file rows; only creates "
            "a short-lived transfer session and optional gzip staging on the adapter side. "
            "When ``lock_mode`` is not ``none``, the daemon registers a runtime lock session, "
            "takes a cooperative sidecar advisory lock before creating the transfer, binds it "
            "to ``transfer_id``, and releases it from adapter hooks when the download reaches "
            "COMPLETED (also best-effort on ack, expiry, and terminal transfer errors)."
        ),
        "parameters": {
            "file_id": {
                "description": (
                    "UUID primary key of the ``files`` row. **Required.** Project and path are "
                    "resolved from this row."
                ),
                "type": "string",
                "required": True,
                "examples": ["f1e2d3c4-b5a6-4789-8012-3456789abcde"],
            },
            "project_id": {
                "description": (
                    "Optional project UUID. When provided, the ``files`` row must belong to "
                    "this project."
                ),
                "type": "string",
                "required": False,
                "examples": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
                "notes": "Discover via list_projects.",
            },
            "compression": {
                "description": "Wire encoding for chunk responses.",
                "type": "string",
                "required": True,
                "enum": ["identity", "gzip"],
            },
            "chunk_size": {
                "description": "Optional hint for per-chunk byte size; server may clamp.",
                "type": "integer",
                "required": False,
                "notes": "Omit to use server defaults.",
            },
            "include_backup_history": {
                "description": (
                    "Include ``old_code`` version list for the resolved project-relative path."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
            },
            "lock_mode": {
                "description": (
                    "Advisory transfer lock. ``none`` — no lock (client ``lock=false``). "
                    "``full`` — exclusive flock until download completes (client ``lock=true``). "
                    "``block_write`` — shared flock (advanced). Requires ``session_id`` when not "
                    "``none``."
                ),
                "type": "string",
                "required": False,
                "default": "none",
                "enum": ["none", "block_write", "full"],
                "notes": "Client ``FileSessionClient.download`` exposes this as boolean ``lock``.",
            },
            "session_id": {
                "description": (
                    "Client session from ``session_create``. Required when ``lock_mode`` is not "
                    "``none``."
                ),
                "type": "string",
                "required": False,
            },
            "job_id": {
                "description": "Optional queue job id for adapter/WebSocket correlation.",
                "type": "string",
                "required": False,
            },
            "correlation_id": {
                "description": "Optional opaque id echoed on the transfer session.",
                "type": "string",
                "required": False,
            },
        },
        "return_value": {
            "success": {
                "description": (
                    "Download session registered. Top-level MCP envelope wraps ``data``; inside "
                    "``data`` expect the same core fields as ``transfer_download_begin`` "
                    "(e.g. ``transfer_id``, ``filename``, ``size_bytes``, ``checksum_algorithm``, "
                    "``checksum_value``, ``compression``, ``chunk_size``, ``offset``, "
                    "``status``, ``plaintext_size_bytes``, ``expires_at``) plus "
                    "``transport``, ``file_id``, ``project_id``, ``file_path``, and optionally "
                    "``backup_history``."
                ),
                "data": {
                    "success": "Omitted in data dict; outer SuccessResult indicates success.",
                    "transfer_id": "Session id for GET /api/transfer/downloads/.../chunks.",
                    "filename": "Suggested leaf name (from project-relative path).",
                    "size_bytes": "Wire size in bytes (compressed when compression is gzip).",
                    "checksum_algorithm": "Typically sha256 (plaintext of the file).",
                    "checksum_value": "Hex digest of the uncompressed file.",
                    "compression": "identity or gzip as requested.",
                    "chunk_size": "Effective chunk size hint after clamping.",
                    "transport": (
                        "Object with chunk_method (GET), chunk_path_template, protocol_hint."
                    ),
                    "file_id": "``files.id`` for the downloaded row.",
                    "project_id": "Effective project UUID (from the ``files`` row).",
                    "file_path": "Project-relative POSIX path resolved from the ``files`` row.",
                    "lock_mode": "Requested lock mode.",
                    "lock_session_id": "Runtime lock session that owns a non-none transfer lock.",
                    "backup_history": (
                        "List of dicts (uuid, timestamp, size_bytes, size_lines, command, "
                        "comment, related_files) when include_backup_history is true; else omitted."
                    ),
                },
                "example": {
                    "transfer_id": "tr_01234567-89ab-cdef-0123-456789abcdef",
                    "filename": "app.py",
                    "size_bytes": 1024,
                    "checksum_algorithm": "sha256",
                    "checksum_value": "a" * 64,
                    "compression": "identity",
                    "chunk_size": 1048576,
                    "offset": 0,
                    "status": "ready",
                    "plaintext_size_bytes": 1024,
                    "transport": {
                        "chunk_method": "GET",
                        "chunk_path_template": (
                            "/api/transfer/downloads/{transfer_id}/chunks?"
                            "offset={offset}&limit={limit}"
                        ),
                        "protocol_hint": "same_as_jsonrpc",
                    },
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "file_path": "src/app.py",
                    "backup_history": [
                        {
                            "uuid": "b2c3d4e5-f6a7-4890-bcde-f12345678901",
                            "timestamp": "2026-05-01T12-00-00",
                            "size_bytes": 1000,
                            "size_lines": 40,
                            "command": "universal_file_save",
                            "comment": "Before edit",
                            "related_files": [],
                        }
                    ],
                },
            },
            "error": {
                "description": "Command or transfer layer rejected the request.",
                "code": (
                    "String codes: PROJECT_NOT_FOUND, FILE_NOT_FOUND, FILE_DELETED, "
                    "FILE_PATH_MISSING, PATH_ERROR, VALIDATION_ERROR (missing file_id or "
                    "unsupported file_path); or JSON-RPC-style integer codes from adapter "
                    "transfer validation (-32602) / transfer domain (-32000)."
                ),
                "message": "Human-readable explanation.",
                "details": "Structured fields (project_id, file_id, missing_or_invalid_fields, etc.).",
            },
        },
        "usage_examples": [
            {
                "description": "Download existing file with advisory lock (client lock=true)",
                "command": {
                    "session_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "compression": "identity",
                    "lock_mode": "full",
                },
                "explanation": (
                    "Id-only mode. Equivalent to ``FileSessionClient.download(..., lock=True)``. "
                    "Lock is released when the adapter finishes streaming chunks."
                ),
            },
            {
                "description": "Download without locking (client lock=false)",
                "command": {
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "compression": "identity",
                    "lock_mode": "none",
                },
                "explanation": "Read-only transfer; no advisory flock.",
            },
            {
                "description": "Download by file_id only (project from DB row)",
                "command": {
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "compression": "identity",
                },
                "explanation": (
                    "``project_id`` must be omitted. Equivalent to ``FileSessionClient.download``."
                ),
            },
        ],
        "error_cases": {
            "PROJECT_NOT_FOUND": {
                "description": "No registered project for the given project_id.",
                "message": "Project {project_id} not found",
                "solution": "Call list_projects and pass a valid UUID.",
            },
            "FILE_NOT_FOUND": {
                "description": (
                    "No ``files`` row for the given ``file_id``, or no row for ``file_id`` + "
                    "``project_id`` when ``project_id`` was supplied."
                ),
                "message": "No file with id … (optionally in project …)",
                "solution": "Refresh indexes or list DB/file entities; use a valid ``files.id``.",
            },
            "FILE_DELETED": {
                "description": "Row exists but is marked deleted (tombstone).",
                "message": "File is marked deleted in the database",
                "solution": "Restore or pick another file_id; do not use deleted rows.",
            },
            "FILE_PATH_MISSING": {
                "description": "Row has empty relative_path and path.",
                "message": "File row has no path",
                "solution": "Repair database or re-index the project.",
            },
            "PATH_ERROR": {
                "description": "Resolved path missing, not a file, or escapes project root.",
                "message": "ValidationError text from path resolver",
                "solution": "Ensure watcher/DB path matches disk; fix broken rows.",
            },
            "InvalidRequest": {
                "description": "Transfer payload rejected (e.g. bad compression enum).",
                "message": "Request validation failed",
                "solution": "Fix parameters; check details.missing_or_invalid_fields.",
            },
            "TRANSFER_DOMAIN": {
                "description": "TransferTooLargeError, TransferCompressionError, or TransferError.",
                "message": "Adapter-specific message in ErrorResult.details",
                "solution": "Retry with different compression or smaller file per server limits.",
            },
            "VALIDATION_ERROR": {
                "description": (
                    "Missing ``file_id``, unsupported ``file_path``, or optional ``project_id`` "
                    "does not match the file row."
                ),
                "message": "ValidationError text (file_id required or file_path not supported).",
                "solution": "Pass ``file_id`` from ``list_project_files``; do not send ``file_path``.",
            },
        },
        "best_practices": [
            "Always verify checksum_value after the full download.",
            "Obtain ``file_id`` from ``list_project_files`` before calling download.",
            "Use ``lock_mode=full`` + ``session_id`` for edit workflows; ``none`` for read-only.",
            "Client ``lock`` boolean maps to ``full`` / ``none``.",
            "Use include_backup_history when auditing which old_code backup matches a baseline.",
            "Prefer gzip on large text files; identity for already-compressed blobs.",
            "Do not cache transfer_id long; sessions expire per adapter configuration.",
        ],
    }


def get_project_file_transfer_upload_save_metadata(cls: Type[Any]) -> Dict[str, Any]:
    """Documentation-oriented metadata for ``project_file_transfer_upload_save``."""
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "category": cls.category,
        "author": cls.author,
        "email": cls.email,
        "detailed_description": (
            "End-to-end **write** path for large bodies without putting them in JSON-RPC: "
            "first complete the adapter **upload** transfer (begin → PUT chunks → complete), "
            "then call this command with ``transfer_id``.\n\n"
            "**Selector modes (exactly one):**\n"
            "- **Update existing** — ``file_id`` only. Project and path come from the ``files`` "
            "row. Optional ``project_id`` must match that row when provided.\n"
            "- **Create new** — ``project_id`` + ``file_path``. Path must **not** already be "
            "indexed (``FILE_ALREADY_INDEXED`` otherwise).\n\n"
            "**Client façade:** ``FileSessionClient.upload`` (update) and ``.upload_new`` "
            "(create). Boolean ``unlock`` maps to ``unlock_after_write`` (default ``true``).\n\n"
            "The implementation reads the committed buffer (gzip or identity), then delegates "
            "to ``UniversalFileSaveCommand`` with the resolved project-relative path.\n\n"
            "**Safety / parity with local editing:** "
            "With default ``backup=true`` and ``dry_run=false``, behavior matches "
            "``universal_file_save`` for the same extension: ``old_code`` backups where "
            "required, handler validation (Python CST path, JSON/YAML parse, etc.), "
            "file metadata updates, and optional git commit via ``commit_message``.\n\n"
            "**Undo:** Restoring prior content is done the same way as after any "
            "``universal_file_save`` (e.g. restore_backup_file / old_code), not by reversing "
            "the transfer buffer.\n\n"
            "**Transfer locks:** ``unlock_after_write`` defaults to true (client ``unlock=true``). "
            "After a successful non-dry-run save the command releases runtime locks bound to "
            "``transfer_id`` and ``session_file_locks`` when ``session_id`` is set. Set "
            "``unlock_after_write=false`` when the caller releases locks manually."
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "**New-file mode:** required with ``file_path`` when ``file_id`` is omitted. "
                    "**Update mode:** omit when ``file_id`` is set; if provided, the ``files`` "
                    "row must belong to this project."
                ),
                "type": "string",
                "required": False,
                "examples": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
                "notes": "Discover via list_projects.",
            },
            "file_id": {
                "description": (
                    "**Update mode:** target ``files.id`` — pass alone to overwrite an existing "
                    "indexed file. Mutually exclusive with ``file_path``."
                ),
                "type": "string",
                "required": False,
                "examples": ["f1e2d3c4-b5a6-4789-8012-3456789abcde"],
            },
            "file_path": {
                "description": (
                    "**New-file mode:** target path relative to project root. Required with "
                    "``project_id`` when ``file_id`` is omitted. Path must not already be in "
                    "``files`` — use ``file_id`` to update. After save, ``file_id`` is returned."
                ),
                "type": "string",
                "required": False,
                "examples": ["notes/draft.md"],
            },
            "transfer_id": {
                "description": "Completed upload session id from transfer_upload_complete.",
                "type": "string",
                "required": True,
                "examples": ["tr_01234567-89ab-cdef-0123-456789abcdef"],
            },
            "dry_run": {
                "description": "Preview validation without writing or backups.",
                "type": "boolean",
                "required": False,
                "default": False,
                "notes": "Use before first apply on production trees.",
            },
            "diff": {
                "description": "Request unified diff in the handler result when supported.",
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "backup": {
                "description": "Enable handler/BackupManager backups before overwrite.",
                "type": "boolean",
                "required": False,
                "default": True,
                "notes": "Disabling skips history parity with normal saves; avoid unless necessary.",
            },
            "commit_message": {
                "description": "Optional git commit message after successful write.",
                "type": "string",
                "required": False,
            },
            "diff_context_lines": {
                "description": "Unified diff context lines when diff is true.",
                "type": "integer",
                "required": False,
            },
            "validate_syntax_only": {
                "description": "Python handler: reduce checks to syntax validation when supported.",
                "type": "boolean",
                "required": False,
                "default": False,
            },
            "tree_id": {
                "description": "Optional CST tree id for Python save path.",
                "type": "string",
                "required": False,
            },
            "unlock_after_write": {
                "description": (
                    "Release runtime transfer and session file locks after successful non-dry-run "
                    "save. Client ``unlock=true`` (default). Set ``false`` to keep locks for manual "
                    "release via ``session_close_file``."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
                "notes": "Client ``FileSessionClient.upload`` / ``upload_new`` expose this as boolean ``unlock``.",
            },
            "lock_mode": {
                "description": (
                    "Optional save-scoped advisory lock: none, block_write (shared), or full "
                    "(exclusive)."
                ),
                "type": "string",
                "required": False,
                "default": "none",
                "enum": ["none", "block_write", "full"],
            },
        },
        "return_value": {
            "success": {
                "description": (
                    "Same semantics as ``universal_file_save`` success payload inside ``data``, "
                    "plus ``file_id`` (always present after a successful non-dry-run save) and "
                    "``resolved_file_path`` when the inner result is a dict."
                ),
                "data": {
                    "success": "Typically True inside data.",
                    "handler_id": "text | json | yaml | python from registry.",
                    "operation": "save",
                    "file_path": "Project-relative path passed to the handler.",
                    "resolved_file_path": "Resolved project-relative path for the target.",
                    "file_id": (
                        "``files.id`` UUID string. After a successful non-dry-run save this field "
                        "is always set: from the existing row or from auto-registration when the "
                        "path was not yet indexed."
                    ),
                    "project_id": "Effective project UUID for the save.",
                    "changed": "Whether content differed from previous file.",
                    "dry_run": "Whether this was a preview run.",
                    "backup_uuid": "Present when a backup was created (handler-dependent).",
                    "diff": "Unified diff string when diff=true and supported.",
                    "lock_mode": "Requested save-scoped lock mode.",
                    "lock_released": "True when unlock_after_write cleanup ran after a save.",
                },
                "example": {
                    "success": True,
                    "handler_id": "python",
                    "operation": "save",
                    "file_path": "src/app.py",
                    "resolved_file_path": "src/app.py",
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "changed": True,
                    "dry_run": False,
                },
            },
            "error": {
                "description": "Transfer read failure, resolver failure, or handler/save failure.",
                "code": (
                    "TRANSFER_NOT_FOUND, TRANSFER_NOT_COMPLETE, BUFFER_READ_ERROR, IMPORT_ERROR, "
                    "FILE_NOT_FOUND, FILE_DELETED, FILE_PATH_MISSING, UNSUPPORTED_FILE_EXTENSION, "
                    "BACKUP_REQUIRED, VALIDATION_ERROR, UNIVERSAL_FILE_SAVE_ERROR, PATH_ERROR, "
                    "or nested universal_file_save codes in details."
                ),
                "message": "Human-readable error.",
                "details": "transfer_id, file_path, handler_id, or handler-specific fields.",
            },
        },
        "usage_examples": [
            {
                "description": "Update existing indexed file (client upload)",
                "command": {
                    "session_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "transfer_id": "tr_01234567-89ab-cdef-0123-456789abcdef",
                    "backup": True,
                    "unlock_after_write": True,
                },
                "explanation": (
                    "Id-only update mode. Equivalent to ``FileSessionClient.upload(..., unlock=True)``."
                ),
            },
            {
                "description": "Update without releasing locks (client unlock=false)",
                "command": {
                    "session_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "transfer_id": "tr_01234567-89ab-cdef-0123-456789abcdef",
                    "unlock_after_write": False,
                },
                "explanation": "Caller must release locks manually after save.",
            },
            {
                "description": "Preview only",
                "command": {
                    "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "transfer_id": "tr_01234567-89ab-cdef-0123-456789abcdef",
                    "dry_run": True,
                    "diff": True,
                },
                "explanation": "Validates handler without writing; may include diff when supported.",
            },
            {
                "description": "Create new file at path (client upload_new)",
                "command": {
                    "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "file_path": "notes/draft.md",
                    "transfer_id": "tr_01234567-89ab-cdef-0123-456789abcdef",
                },
                "explanation": (
                    "New-file mode. Path must not already be in ``files``. Returns new ``file_id``."
                ),
            },
            {
                "description": "Save upload buffer using ``file_id`` only",
                "command": {
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "transfer_id": "tr_01234567-89ab-cdef-0123-456789abcdef",
                },
                "explanation": (
                    "Update mode. ``project_id`` and ``file_path`` must be omitted."
                ),
            },
        ],
        "error_cases": {
            "TRANSFER_NOT_FOUND": {
                "description": "Unknown or expired upload session id.",
                "message": "Transfer not found or expired: ...",
                "solution": "Re-upload; ensure transfer_upload_complete succeeded.",
            },
            "TRANSFER_NOT_COMPLETE": {
                "description": "Session exists but upload not finalized.",
                "message": "Transfer not ready: ...",
                "solution": "Call transfer_upload_complete after all PUT chunks.",
            },
            "BUFFER_READ_ERROR": {
                "description": "Cannot read or decode buffer (e.g. encoding, corrupt gzip).",
                "message": "Failed to read transfer buffer: ...",
                "solution": "Re-upload with valid UTF-8 text or matching compression.",
            },
            "IMPORT_ERROR": {
                "description": "mcp_proxy_adapter not available in the server process.",
                "message": "mcp_proxy_adapter not available: ...",
                "solution": "Fix server environment / package install.",
            },
            "FILE_NOT_FOUND": {
                "description": (
                    "No ``files`` row for the given ``file_id``, or no row for ``file_id`` + "
                    "``project_id`` when ``project_id`` was supplied."
                ),
                "message": "No file with id …",
                "solution": "Use a valid ``files.id``; if ``project_id`` is set, it must match the row.",
            },
            "FILE_DELETED": {
                "description": "Target row is tombstoned.",
                "message": "File is marked deleted in the database",
                "solution": "Restore the file row or choose another id.",
            },
            "UNSUPPORTED_FILE_EXTENSION": {
                "description": "Extension not handled by the universal registry.",
                "message": "From RegistryError / universal_file_save",
                "solution": "Use a supported type or a different command.",
            },
            "BACKUP_REQUIRED": {
                "description": "Backup to old_code failed; save aborted (text path).",
                "message": "Backup to old_code ... mandatory",
                "solution": "Fix old_code permissions/disk; retry with backup=true.",
            },
            "UNIVERSAL_FILE_SAVE_ERROR": {
                "description": "Unexpected exception inside universal_file_save.",
                "message": "universal_file_save failed: ...",
                "solution": "Inspect logs; fix content or handler constraints.",
            },
            "VALIDATION_ERROR": {
                "description": (
                    "Invalid selector combination, or ``file_id`` omitted but ``project_id`` / "
                    "``file_path`` missing."
                ),
                "message": "ValidationError text from the command.",
                "solution": (
                    "Update: ``file_id`` only. New file: ``project_id`` + ``file_path``; path "
                    "must not be indexed yet."
                ),
            },
            "FILE_ALREADY_INDEXED": {
                "description": (
                    "New-file mode: ``project_id`` + ``file_path`` was sent but the path already "
                    "has a row in ``files``."
                ),
                "message": "Path … is already indexed; use file_id to update",
                "solution": (
                    "Use ``file_id`` (update mode / client ``upload``) instead of ``file_path``."
                ),
            },
        },
        "best_practices": [
            "Complete transfer_upload_complete before calling this command.",
            "Update existing files with ``file_id`` only (client ``upload``).",
            "Create new files with ``project_id`` + ``file_path`` only (client ``upload_new``).",
            "Do not use path mode for paths already in ``list_project_files`` — use ``file_id``.",
            "Use dry_run=true and diff=true on risky Python/JSON/YAML changes first.",
            "Keep backup=true so old_code history stays consistent with local saves.",
            "Keep unlock_after_write=true (client unlock=true) unless managing locks manually.",
            "Omit commit_message unless git integration is desired for this change.",
        ],
    }
