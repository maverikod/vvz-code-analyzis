"""
Shared imports for project management MCP command modules.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.exceptions import ValidationError
from ...core.project_resolution import ProjectIdError, load_project_id
from ..base_mcp_command import BaseMCPCommand, _get_socket_path_from_db_path

logger = logging.getLogger(__name__)

__all__ = [
    "Any",
    "BaseMCPCommand",
    "Dict",
    "ErrorResult",
    "List",
    "Optional",
    "Path",
    "SuccessResult",
    "ValidationError",
    "ProjectIdError",
    "load_project_id",
    "_get_socket_path_from_db_path",
    "logger",
    "uuid",
]
