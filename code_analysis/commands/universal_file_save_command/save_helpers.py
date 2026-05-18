"""
MCP command: universal_file_save

Registry-first full-file save: routes by extension to text, JSON, YAML, or Python
handlers. Resolves handler before validation, backup, or writes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Type
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult
from .base_mcp_command import BaseMCPCommand
from .project_text_file_guard import reject_if_write_under_project_venv
from .registration import (
    MCP_FILE_MANAGEMENT_REGISTRY_HELP,
    REGISTRY_SCHEMA_DISCOVERY_SHORT,
)
from ..core.backup_manager import BackupManager
from ..core.git_integration import commit_after_write
from ..core.exceptions import ValidationError
from ..core.file_handlers.base import FileHandlerRequest, FileHandlerResult
from ..core.file_handlers.json_handler import JsonFileHandler
from ..core.file_handlers.python_handler import PythonFileHandler
from ..core.file_handlers.registry import (
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_YAML,
    RegistryError,
    resolve_handler,
)
from ..core.file_handlers.text_handler import (
    TextFileHandler,
    persist_plain_text_file_metadata,
)
from ..core.file_handlers.yaml_handler import YamlFileHandler
from ..core.file_lock import file_lock
from ..core.path_normalization import normalize_path_simple

def _success_from_handler(fr: FileHandlerResult, *, operation: str) -> SuccessResult:
    data: Dict[str, Any] = {
        "success": True,
        "handler_id": fr.handler_id,
        "operation": operation,
        "file_path": fr.file_path,
        "project_id": fr.project_id,
        "dry_run": fr.dry_run,
        "changed": fr.changed,
    }
    data.update(fr.data)
    return SuccessResult(data=data)



def _error_from_handler(fr: FileHandlerResult) -> ErrorResult:
    return ErrorResult(
        message=fr.message or fr.code,
        code=fr.code or "VALIDATION_FAILED",
        details=fr.details
        or {
            "file_path": fr.file_path,
            "handler_id": fr.handler_id,
            "operation": fr.operation,
        },
    )



