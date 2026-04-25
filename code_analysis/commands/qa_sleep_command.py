"""
Deterministic test command for queue stop lifecycle verification.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult


class QASleepCommand(Command):
    """Sleep in small steps and print heartbeat logs."""

    name = "qa_sleep"
    descr = "Deterministic sleep command for queue lifecycle regression tests"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "seconds": {"type": "number", "default": 30.0},
                "tick_seconds": {"type": "number", "default": 0.5},
            },
        }

    async def execute(
        self, seconds: float = 30.0, tick_seconds: float = 0.5, **kwargs: Any
    ) -> SuccessResult:
        total = max(0.0, float(seconds))
        tick = max(0.1, float(tick_seconds))
        started = time.time()
        elapsed = 0.0
        while elapsed < total:
            print(f"qa_sleep heartbeat elapsed={elapsed:.1f}s", flush=True)
            await asyncio.sleep(min(tick, total - elapsed))
            elapsed = time.time() - started
        return SuccessResult(data={"slept_seconds": round(elapsed, 2), "success": True})
