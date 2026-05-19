"""
Central MCP registration for ``file_management`` universal and legacy commands.

Registers :mod:`code_analysis.commands.universal_file_*` first-class commands and legacy
compat wrappers (**``read_project_text_file``**, **``write_project_text_lines``**).

Handlers and documentation-oriented schema fragments live in
``code_analysis.core.file_handlers.registry``: **``get_handler_schema(handler_id, operation)``**,
``list_handler_mappings()``, ``HANDLER_IDS``.

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
    "Legacy **read_project_text_file** / **write_project_text_lines** are compatibility "
    "wrappers — they **must not** be treated as alternate editors for source code "
    "(``.py``, ``.pyi``, …), ``.json``, ``.yaml``, or other structured formats; route those "
    "through universal_file_read, universal_file_save, universal_file_replace, "
    "universal_file_delete, and JSON/YAML/Python/CST tooling as documented."
)

# Compact line for embedding in JSON-schema ``description`` fields (helps MCP help payloads).
REGISTRY_SCHEMA_DISCOVERY_SHORT = (
    "Discovery: code_analysis.core.file_handlers.registry.get_handler_schema(handler_id, operation) "
    "and list_handler_mappings(); handler ids text, json, yaml, python."
)


def register_file_management_commands(reg: Any) -> None:
    """Register universal file commands and legacy text compat commands.

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
