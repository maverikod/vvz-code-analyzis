"""
MCP command wrapper for code_mapper (index update).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..code_mapper import CodeMapper

logger = logging.getLogger(__name__)


class UpdateIndexesMCPCommand(Command):
    """Update code indexes using code_mapper (analyze project and generate reports)."""

    name = "update_indexes"
    version = "1.0.0"
    descr = (
        "Update code indexes using code_mapper (analyze project and generate reports)"
    )
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = True  # This can be long-running, use queue

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Root directory to analyze",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for reports (default: code_analysis)",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines per file threshold",
                    "default": 400,
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        output_dir: Optional[str] = None,
        max_lines: int = 400,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute code mapper index update.

        Args:
            root_dir: Root directory to analyze
            output_dir: Optional output directory for reports
            max_lines: Maximum lines per file threshold

        Returns:
            SuccessResult with update results or ErrorResult on failure
        """
        try:
            root_path = Path(root_dir).resolve()
            if not root_path.exists() or not root_path.is_dir():
                return ErrorResult(
                    message=f"Root directory does not exist or is not a directory: {root_dir}",
                    code="INVALID_PATH",
                )

            # Default output_dir to code_analysis subdirectory
            if not output_dir:
                output_dir = str(root_path / "code_analysis")
            else:
                output_dir = str(Path(output_dir).resolve())

            # Run code_mapper in executor to avoid blocking
            def run_code_mapper():
                mapper = CodeMapper(
                    root_dir=str(root_path),
                    output_dir=output_dir,
                    max_lines=max_lines,
                    use_sqlite=True,
                )
                mapper.analyze_directory(str(root_path))
                mapper.generate_reports()
                return mapper

            loop = asyncio.get_event_loop()
            mapper = await loop.run_in_executor(None, run_code_mapper)

            return SuccessResult(
                data={
                    "root_dir": str(root_path),
                    "output_dir": output_dir,
                    "max_lines": max_lines,
                    "message": "Indexes updated successfully",
                }
            )

        except Exception as e:
            logger.exception(f"Error updating indexes: {e}")
            return ErrorResult(
                message=f"Failed to update indexes: {str(e)}",
                code="INDEX_UPDATE_ERROR",
                details={"error": str(e)},
            )
