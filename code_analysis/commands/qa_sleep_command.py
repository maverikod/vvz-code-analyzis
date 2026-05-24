"""
Deterministic test command for queue stop lifecycle verification.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult
from mcp_proxy_adapter.core.errors import ValidationError


class QASleepCommand(Command):
    """Sleep in small steps and print heartbeat logs."""

    name = "qa_sleep"
    version = "1.0.0"
    descr = "Deterministic sleep command for queue lifecycle regression tests"
    category = "qa"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "number",
                    "default": 30.0,
                    "minimum": 0,
                    "description": "Total sleep duration in seconds.",
                },
                "tick_seconds": {
                    "type": "number",
                    "default": 0.5,
                    "minimum": 0.1,
                    "description": "Heartbeat log interval while sleeping.",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["QASleepCommand"]) -> Dict[str, Any]:
        from code_analysis.commands.zero_arg_commands_metadata import (
            qa_sleep_command_metadata,
        )

        return qa_sleep_command_metadata(cls)

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Adapter Command validates types and schema bounds; reject OOB instead of clamp."""
        return super().validate_params(params)

    async def execute(
        self, seconds: float = 30.0, tick_seconds: float = 0.5, **kwargs: Any
    ) -> SuccessResult | ErrorResult:
        params: Dict[str, Any] = {
            "seconds": seconds,
            "tick_seconds": tick_seconds,
        }
        params.update({k: v for k, v in kwargs.items() if k != "context"})
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            data = getattr(e, "data", None) or {}
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details={"field": data.get("field")},
            )
        total = float(params.get("seconds", 30.0))
        tick = float(params.get("tick_seconds", 0.5))
        started = time.time()
        elapsed = 0.0
        while elapsed < total:
            print(f"qa_sleep heartbeat elapsed={elapsed:.1f}s", flush=True)
            await asyncio.sleep(min(tick, total - elapsed))
            elapsed = time.time() - started
        return SuccessResult(data={"slept_seconds": round(elapsed, 2), "success": True})
