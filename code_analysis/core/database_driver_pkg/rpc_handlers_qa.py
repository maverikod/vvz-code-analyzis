"""
QA-only RPC handlers (gated by environment).

Used for deterministic MCP/plan verification of ``[DB_RETRY]`` and related paths.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from code_analysis.core.database_client.protocol import (
    ErrorCode,
    ErrorResult,
    SuccessResult,
)

from .exceptions import DriverOperationError


def _qa_mcp_hooks_enabled() -> bool:
    v = (os.environ.get("CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


class _RPCHandlersQAMixin:
    """Mixin: QA RPC methods. Concrete class must set ``self.driver``."""

    driver: Any

    def handle_qa_set_db_retry_injections(
        self, params: Dict[str, Any]
    ) -> SuccessResult | ErrorResult:
        """Arm the driver to raise a synthetic transient on the next N self-managed writes."""
        if not _qa_mcp_hooks_enabled():
            return ErrorResult(
                error_code=ErrorCode.PERMISSION_DENIED,
                description=(
                    "qa_set_db_retry_injections is disabled; set "
                    "CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1 on the database driver process"
                ),
            )
        raw = params.get("remaining", 1)
        try:
            n = int(raw)
        except (TypeError, ValueError):
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description="remaining must be an integer",
            )
        try:
            data = self.driver.qa_set_db_retry_injections(n)
        except DriverOperationError as e:
            return ErrorResult(
                error_code=ErrorCode.VALIDATION_ERROR,
                description=str(e),
            )
        except Exception as e:
            return ErrorResult(
                error_code=ErrorCode.DATABASE_ERROR,
                description=str(e),
            )
        if isinstance(data, dict):
            return SuccessResult(data=data)
        return SuccessResult(data={"success": True, "payload": data})
