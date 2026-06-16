"""
Central MCP registration for ``file_management`` transfer and lock helpers.

This server owns watched project trees, the project index database, client
sessions, DB file locks, and on-disk ``.lock`` sidecars. External editors call
these commands to download/upload bytes and coordinate locks; they do not run
structured content editing here.

**Content editing is not registered on this server** (``universal_file_open``,
CST/JSON tree modify/save, ``format_code``, legacy line writers). Read-only
content surface: ``universal_file_preview``, ``get_file_lines``, paginated
``search`` / ``search_*``. Filesystem ops
(``fs_copy`` / ``fs_move`` / ``fs_remove``) are a separate category.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any

# Appended to MCP descr / schemas so models steer to handler routing vs plain-text pitfalls.
MCP_FILE_MANAGEMENT_REGISTRY_HELP = (
    "Use ``code_analysis.core.file_handlers.registry.get_handler_schema(handler_id, operation)`` "
    "for per-handler request hints and ``list_handler_mappings()`` for suffix→handler rows "
    "(handler ids: text, json, yaml, python). "
    "File **content editing** is not on this server; use ``universal_file_preview`` "
    "for inspection and ``search`` for project-wide lookup. Editors use ``session_*``, "
    "``project_file_transfer_*``, and ``project_file_advisory_lock_batch`` here."
)

# Compact line for embedding in JSON-schema ``description`` fields (helps MCP help payloads).
REGISTRY_SCHEMA_DISCOVERY_SHORT = (
    "Discovery: code_analysis.core.file_handlers.registry.get_handler_schema(handler_id, operation) "
    "and list_handler_mappings(); handler ids text, json, yaml, python."
)


def register_file_management_commands(reg: Any) -> None:
    """Register transfer and lock helpers (no content-edit commands).

    Commands use ``category = 'file_management'`` on classes; MCP help groups by category.

    Args:
        reg: ``mcp_proxy_adapter.commands.command_registry.registry`` implementation.
    """
    from .project_file_transfer_by_id_commands import (
        ProjectFileTransferDownloadBeginCommand,
        ProjectFileTransferUploadSaveCommand,
    )
    from .project_file_advisory_lock_batch_command import (
        ProjectFileAdvisoryLockBatchCommand,
    )
    from .project_file_lock_status_command import ProjectFileLockStatusCommand

    reg.register(ProjectFileAdvisoryLockBatchCommand, "custom")
    reg.register(ProjectFileLockStatusCommand, "custom")
    reg.register(ProjectFileTransferDownloadBeginCommand, "custom")
    reg.register(ProjectFileTransferUploadSaveCommand, "custom")
