"""
Public async client for code-analysis-server (JSON-RPC via mcp-proxy-adapter).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from code_analysis_client.client import CodeAnalysisAsyncClient
from code_analysis_client.commands_proxy import ValidatedCommandsProxy
from code_analysis_client.config import (
    adapter_settings_from_server_config,
    adapter_settings_to_jsonrpc_kwargs,
    load_server_config,
)
from code_analysis_client.exceptions import (
    ClientValidationError,
    CommandFailedError,
    JobFailedError,
    JobTimeoutError,
    QueueJobError,
)
from code_analysis_client.file_session import FileSessionClient, SessionNotFoundError
from code_analysis_client.queue_wait import (
    QueuedJob,
    extract_job_id,
    is_queued_envelope,
    unwrap_job_result,
    wait_for_job,
)
from code_analysis_client.server_api import (
    CLIENT_FACADE_COMMANDS,
    CST_REMOVED_COMMANDS,
    FILE_SESSION_COMMANDS,
    FILE_SESSION_FACADE_METHODS,
    LEGACY_REMOVED_COMMANDS,
    REMOVED_COMMANDS,
    TRANSFER_FACADE_METHODS,
    UNIVERSAL_FILE_COMMANDS,
)
from code_analysis_client.universal_file import UniversalFileClient
from code_analysis_client.server_schema import (
    fetch_command_schema_from_server,
    parse_schema_from_help_payload,
)
from code_analysis_client.validation import (
    prepare_params_for_schema,
    validate_params_against_schema,
)

__all__ = [
    "CLIENT_FACADE_COMMANDS",
    "CST_REMOVED_COMMANDS",
    "ClientValidationError",
    "CodeAnalysisAsyncClient",
    "CommandFailedError",
    "FILE_SESSION_COMMANDS",
    "FILE_SESSION_FACADE_METHODS",
    "FileSessionClient",
    "JobFailedError",
    "JobTimeoutError",
    "LEGACY_REMOVED_COMMANDS",
    "QueueJobError",
    "QueuedJob",
    "REMOVED_COMMANDS",
    "SessionNotFoundError",
    "TRANSFER_FACADE_METHODS",
    "UNIVERSAL_FILE_COMMANDS",
    "UniversalFileClient",
    "ValidatedCommandsProxy",
    "adapter_settings_from_server_config",
    "adapter_settings_to_jsonrpc_kwargs",
    "extract_job_id",
    "fetch_command_schema_from_server",
    "is_queued_envelope",
    "load_server_config",
    "parse_schema_from_help_payload",
    "prepare_params_for_schema",
    "unwrap_job_result",
    "validate_params_against_schema",
    "wait_for_job",
]


def _read_package_version() -> str:
    """Read installed client version from version.txt or package metadata."""
    vf = Path(__file__).resolve().parent / "version.txt"
    if vf.is_file():
        return vf.read_text(encoding="utf-8").strip()
    try:
        import importlib.metadata as _imd

        return _imd.version("code-analysis-client")
    except Exception:
        return "0.0.0"


__version__ = _read_package_version()
