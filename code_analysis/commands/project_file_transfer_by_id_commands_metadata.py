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
            "Maps a project file to the mcp-proxy-adapter **download transfer** flow. "
            "Provide **either** ``file_id`` (``files`` primary key) **or** the pair "
            "``project_id`` + ``file_path`` (literal path relative to project root, same as "
            "``list_project_files`` / ``universal_file_read``). When ``file_id`` is set, "
            "``project_id`` and ``file_path`` are optional (optional ``project_id`` filters the "
            "row to that project). When ``file_id`` is omitted, both ``project_id`` and "
            "``file_path`` are required. The server ensures the path stays inside the project "
            "root, checks the file exists on disk, then calls the same session creation logic "
            "as ``transfer_download_begin`` with an absolute ``source_path``.\n\n"
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
            "project_id": {
                "description": (
                    "Project UUID. **Required** with ``file_path`` when ``file_id`` is omitted. "
                    "**Optional** when ``file_id`` is set; if provided, the ``files`` row must "
                    "belong to this project."
                ),
                "type": "string",
                "required": False,
                "examples": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
                "notes": "Discover via list_projects.",
            },
            "file_id": {
                "description": (
                    "UUID primary key of the ``files`` row. Mutually exclusive with ``file_path``."
                ),
                "type": "string",
                "required": False,
                "examples": ["f1e2d3c4-b5a6-4789-8012-3456789abcde"],
            },
            "file_path": {
                "description": (
                    "Project-relative literal path (POSIX). **Required** when ``file_id`` is "
                    "omitted (with ``project_id``). Mutually exclusive with ``file_id``. "
                    "File must exist on disk. Response ``file_id`` is set when the path is indexed."
                ),
                "type": "string",
                "required": False,
                "examples": ["src/app.py", "docs/README.md"],
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
                    "Optional transfer advisory lock: none, block_write (shared flock), or "
                    "full (exclusive flock)."
                ),
                "type": "string",
                "required": False,
                "default": "none",
                "enum": ["none", "block_write", "full"],
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
                    "``backup_history``. ``file_id`` may be null when the call used ``file_path`` "
                    "only and the path is not in the index."
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
                    "file_id": "``files.id`` when known (indexed); null for path-only unindexed.",
                    "project_id": "Effective project UUID (from the request or from the ``files`` row).",
                    "file_path": "Project-relative POSIX path used for disk read.",
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
                    "FILE_PATH_MISSING, PATH_ERROR, VALIDATION_ERROR (e.g. both file_id and "
                    "file_path, neither, or missing project_id/file_path in path mode); or "
                    "JSON-RPC-style integer codes from adapter "
                    "transfer validation (-32602) / transfer domain (-32000)."
                ),
                "message": "Human-readable explanation.",
                "details": "Structured fields (project_id, file_id, missing_or_invalid_fields, etc.).",
            },
        },
        "usage_examples": [
            {
                "description": "Start gzip download for one indexed file",
                "command": {
                    "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "compression": "gzip",
                    "include_backup_history": True,
                },
                "explanation": (
                    "Creates a session; client streams chunks, then verifies checksum_value "
                    "against the decompressed content. backup_history links to prior old_code "
                    "snapshots."
                ),
            },
            {
                "description": "Download without embedding backup list",
                "command": {
                    "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "compression": "identity",
                    "include_backup_history": False,
                },
                "explanation": "Smaller response when version metadata is not needed.",
            },
            {
                "description": "Download by project-relative path (no file_id)",
                "command": {
                    "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "file_path": "src/app.py",
                    "compression": "identity",
                },
                "explanation": (
                    "Same chunked download; ``file_id`` in the response is set when the path is indexed."
                ),
            },
            {
                "description": "Download by ``file_id`` only (project from DB row)",
                "command": {
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "compression": "identity",
                },
                "explanation": (
                    "``project_id`` and ``file_path`` may be omitted; the server resolves the path "
                    "and effective ``project_id`` from the ``files`` row."
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
                    "Invalid selector combination: both ``file_id`` and ``file_path``; neither; "
                    "or ``file_id`` omitted but ``project_id`` or ``file_path`` missing."
                ),
                "message": "ValidationError text (mutual exclusivity or missing project_id/file_path).",
                "solution": (
                    "With ``file_id``: omit ``file_path``; ``project_id`` optional. "
                    "Without ``file_id``: send both ``project_id`` and ``file_path``."
                ),
            },
        },
        "best_practices": [
            "Always verify checksum_value after the full download.",
            "Use ``file_path`` when you already have ``relative_path`` from ``list_project_files``; "
            "use ``file_id`` when you have the UUID from the index.",
            "Use include_backup_history when auditing which old_code backup matches a baseline.",
            "Prefer gzip on large text files to save bandwidth; identity for already-compressed blobs.",
            "Do not cache transfer_id long; sessions expire per adapter configuration.",
            "Use lock_mode=block_write when clients need a stable read while cooperative writers use file_lock.",
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
            "then call this command with ``transfer_id`` and **either** ``file_id`` **or** "
            "the pair ``project_id`` + project-relative ``file_path``. When ``file_id`` is set, "
            "``project_id`` and ``file_path`` are optional. When ``file_id`` is omitted, both "
            "``project_id`` and ``file_path`` are required. The implementation reads the committed "
            "buffer (gzip or identity), then delegates to ``UniversalFileSaveCommand`` with the "
            "resolved project-relative path.\n\n"
            "**Safety / parity with local editing:** "
            "With default ``backup=true`` and ``dry_run=false``, behavior matches "
            "``universal_file_save`` for the same extension: ``old_code`` backups where "
            "required, handler validation (Python CST path, JSON/YAML parse, etc.), "
            "file metadata updates, and optional git commit via ``commit_message``.\n\n"
            "**Undo:** Restoring prior content is done the same way as after any "
            "``universal_file_save`` (e.g. restore_backup_file / old_code), not by reversing "
            "the transfer buffer.\n\n"
            "**Scope:** The target path is always under the resolved project root (from "
            "``project_id`` in path mode, or from the ``files`` row when only ``file_id`` is sent). "
            "``file_id`` mode uses the path from the index row. ``file_path`` mode uses the "
            "literal relative path (new files follow ``universal_file_save`` rules).\n\n"
            "**Transfer locks:** ``unlock_after_write`` defaults to true. After a successful "
            "non-dry-run save the command releases any runtime lock bound to ``transfer_id``. "
            "``lock_mode`` can also acquire a save-scoped lock when no earlier transfer lock "
            "exists; that lock is released after the successful save or on save failure."
        ),
        "parameters": {
            "project_id": {
                "description": (
                    "**Required** with ``file_path`` when ``file_id`` is omitted. **Optional** when "
                    "``file_id`` is set; if provided, the ``files`` row must belong to this project."
                ),
                "type": "string",
                "required": False,
                "examples": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
                "notes": "Discover via list_projects.",
            },
            "file_id": {
                "description": (
                    "Target ``files.id`` (UUID). Mutually exclusive with ``file_path``. When set, "
                    "``project_id`` and ``file_path`` are optional."
                ),
                "type": "string",
                "required": False,
                "examples": ["f1e2d3c4-b5a6-4789-8012-3456789abcde"],
            },
            "file_path": {
                "description": (
                    "Target path relative to project root (literal). **Required** when ``file_id`` "
                    "is omitted (with ``project_id``). Mutually exclusive with ``file_id``. After a "
                    "successful non-dry-run save, ``file_id`` is filled from the index when available."
                ),
                "type": "string",
                "required": False,
                "examples": ["src/app.py"],
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
                    "Release the transfer/file runtime lock after successful non-dry-run save."
                ),
                "type": "boolean",
                "required": False,
                "default": True,
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
                    "plus ``file_id`` and ``resolved_file_path`` when the inner result is a dict."
                ),
                "data": {
                    "success": "Typically True inside data.",
                    "handler_id": "text | json | yaml | python from registry.",
                    "operation": "save",
                    "file_path": "Project-relative path passed to the handler.",
                    "resolved_file_path": "Resolved project-relative path for the target.",
                    "file_id": "``files.id`` when known.",
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
                "description": "Save uploaded buffer to an existing indexed file",
                "command": {
                    "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "transfer_id": "tr_01234567-89ab-cdef-0123-456789abcdef",
                    "backup": True,
                    "dry_run": False,
                },
                "explanation": (
                    "Run after transfer_upload_complete. Creates backups and updates the file "
                    "like universal_file_save."
                ),
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
                "description": "Save upload buffer to a path (no file_id)",
                "command": {
                    "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "file_path": "notes/draft.md",
                    "transfer_id": "tr_01234567-89ab-cdef-0123-456789abcdef",
                },
                "explanation": (
                    "Same as universal_file_save for that relative path; use when you know the path "
                    "from list_project_files."
                ),
            },
            {
                "description": "Save upload buffer using ``file_id`` only",
                "command": {
                    "file_id": "f1e2d3c4-b5a6-4789-8012-3456789abcde",
                    "transfer_id": "tr_01234567-89ab-cdef-0123-456789abcdef",
                },
                "explanation": (
                    "``project_id`` and ``file_path`` may be omitted; the server resolves both from "
                    "the ``files`` row."
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
                    "With ``file_id``: omit ``file_path``; ``project_id`` optional. "
                    "Without ``file_id``: send ``project_id`` and ``file_path``."
                ),
            },
        },
        "best_practices": [
            "Complete transfer_upload_complete before calling this command.",
            "Without ``file_id``, always send both ``project_id`` and ``file_path``; with ``file_id``, "
            "those two are optional.",
            "Use ``file_path`` for the same ``relative_path`` string as ``list_project_files``; "
            "use ``file_id`` when you already have the UUID.",
            "Use dry_run=true and diff=true on risky Python/JSON/YAML changes first.",
            "Keep backup=true so old_code history stays consistent with local saves.",
            "Verify with universal_file_read or project_file_transfer_download_begin after write.",
            "Omit commit_message unless git integration is desired for this change.",
            "Keep unlock_after_write=true unless a caller deliberately manages the runtime lease.",
        ],
    }
