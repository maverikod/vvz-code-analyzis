"""
MCP commands for code refactoring operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.database import CodeDatabase
from .refactor import RefactorCommand as InternalRefactorCommand

logger = logging.getLogger(__name__)


def _open_database(root_dir: str) -> CodeDatabase:
    """Open database connection."""
    db_path = Path(root_dir) / "data" / "code_analysis.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")
    return CodeDatabase(db_path)


def _get_project_id(db: CodeDatabase, root_path: Path, project_id: Optional[str] = None) -> Optional[str]:
    """Get or create project ID."""
    if project_id:
        project = db.get_project(project_id)
        return project_id if project else None
    # Fallback: get or create by root_dir
    return db.get_or_create_project(str(root_path), name=root_path.name)


class SplitClassMCPCommand(Command):
    """Split a class into multiple smaller classes."""

    name = "split_class"
    version = "1.0.0"
    descr = "Split a class into multiple smaller classes"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file (absolute or relative to project root)",
                },
                "config": {
                    "type": "object",
                    "description": "Split configuration (JSON object or string)",
                    "additionalProperties": True,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "file_path", "config"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        config: Any,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            db = _open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = _get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(message="Project not found", code="PROJECT_NOT_FOUND")

            # Parse config if it's a string
            if isinstance(config, str):
                config = json.loads(config)

            cmd = InternalRefactorCommand(proj_id)
            result = await cmd.split_class(str(root_path), file_path, config)
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "split_class failed"),
                code="SPLIT_CLASS_ERROR",
                details=result,
            )
        except Exception as e:
            logger.exception("split_class failed: %s", e)
            return ErrorResult(message=f"split_class failed: {e}", code="SPLIT_CLASS_ERROR")


class ExtractSuperclassMCPCommand(Command):
    """Extract common functionality into base class."""

    name = "extract_superclass"
    version = "1.0.0"
    descr = "Extract common functionality into base class"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to Python file (absolute or relative to project root)",
                },
                "config": {
                    "type": "object",
                    "description": "Extraction configuration (JSON object or string)",
                    "additionalProperties": True,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "file_path", "config"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        config: Any,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            db = _open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = _get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(message="Project not found", code="PROJECT_NOT_FOUND")

            # Parse config if it's a string
            if isinstance(config, str):
                config = json.loads(config)

            cmd = InternalRefactorCommand(proj_id)
            result = await cmd.extract_superclass(str(root_path), file_path, config)
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "extract_superclass failed"),
                code="EXTRACT_SUPERCLASS_ERROR",
                details=result,
            )
        except Exception as e:
            logger.exception("extract_superclass failed: %s", e)
            return ErrorResult(message=f"extract_superclass failed: {e}", code="EXTRACT_SUPERCLASS_ERROR")

