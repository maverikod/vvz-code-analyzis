"""
MCP command wrappers for AST operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult, ErrorResult

from ..core.database import CodeDatabase
from .get_ast import GetASTCommand as InternalGetAST
from .search_ast_nodes import SearchASTNodesCommand as InternalSearchAST
from .ast_statistics import ASTStatisticsCommand as InternalASTStats
from .list_project_files import ListProjectFilesCommand as InternalListFiles
from .get_code_entity_info import GetCodeEntityInfoCommand as InternalGetEntityInfo

logger = logging.getLogger(__name__)


def _open_database(root_dir: str) -> CodeDatabase:
    root_path = Path(root_dir).resolve()
    data_dir = root_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "code_analysis.db"
    return CodeDatabase(db_path)


def _get_project_id(db: CodeDatabase, root_dir: Path, project_id: Optional[str]) -> Optional[str]:
    if project_id:
        project = db.get_project(project_id)
        return project_id if project else None
    # Fallback: get or create by root_dir
    return db.get_or_create_project(str(root_dir), name=root_dir.name)


class GetASTMCPCommand(Command):
    """Retrieve stored AST for a given file."""

    name = "get_ast"
    version = "1.0.0"
    descr = "Get AST for a Python file from the analysis database"
    category = "ast"
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
                "include_json": {
                    "type": "boolean",
                    "description": "Include full AST JSON in response",
                    "default": True,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        include_json: bool = True,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            db = _open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = _get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(message="Project not found", code="PROJECT_NOT_FOUND")

            cmd = InternalGetAST(db, proj_id, file_path, include_json=include_json)
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(message=result.get("message", "AST retrieval failed"), code="GET_AST_ERROR", details=result)
        except Exception as e:
            logger.exception("get_ast failed: %s", e)
            return ErrorResult(message=f"get_ast failed: {e}", code="GET_AST_ERROR")


class SearchASTNodesMCPCommand(Command):
    """Search AST nodes across project/files."""

    name = "search_ast_nodes"
    version = "1.0.0"
    descr = "Search AST nodes (by type) in project files"
    category = "ast"
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
                "node_type": {
                    "type": "string",
                    "description": "AST node type to search (e.g., ClassDef, FunctionDef)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to limit search (absolute or relative)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 100,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        node_type: Optional[str] = None,
        file_path: Optional[str] = None,
        limit: int = 100,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            db = _open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = _get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(message="Project not found", code="PROJECT_NOT_FOUND")

            cmd = InternalSearchAST(db, proj_id, node_type=node_type, file_path=file_path, limit=limit)
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(message=result.get("message", "search_ast_nodes failed"), code="SEARCH_AST_ERROR", details=result)
        except Exception as e:
            logger.exception("search_ast_nodes failed: %s", e)
            return ErrorResult(message=f"search_ast_nodes failed: {e}", code="SEARCH_AST_ERROR")


class ASTStatisticsMCPCommand(Command):
    """Get AST statistics for project or a specific file."""

    name = "ast_statistics"
    version = "1.0.0"
    descr = "Collect AST statistics for project or single file"
    category = "ast"
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
                    "description": "Optional file path to compute stats for (absolute or relative)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: Optional[str] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            db = _open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = _get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(message="Project not found", code="PROJECT_NOT_FOUND")

            cmd = InternalASTStats(db, proj_id, file_path=file_path)
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(message=result.get("message", "ast_statistics failed"), code="AST_STATS_ERROR", details=result)
        except Exception as e:
            logger.exception("ast_statistics failed: %s", e)
            return ErrorResult(message=f"ast_statistics failed: {e}", code="AST_STATS_ERROR")


class ListProjectFilesMCPCommand(Command):
    """List all files in a project with metadata."""

    name = "list_project_files"
    version = "1.0.0"
    descr = "List all files in a project with statistics (classes, functions, chunks, AST)"
    category = "ast"
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
                "file_pattern": {
                    "type": "string",
                    "description": "Optional pattern to filter files (e.g., '*.py', 'core/*')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional limit on number of results",
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination",
                    "default": 0,
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_pattern: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            db = _open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = _get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(message="Project not found", code="PROJECT_NOT_FOUND")

            cmd = InternalListFiles(db, proj_id, file_pattern=file_pattern, limit=limit, offset=offset)
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "list_project_files failed"),
                code="LIST_FILES_ERROR",
                details=result
            )
        except Exception as e:
            logger.exception("list_project_files failed: %s", e)
            return ErrorResult(message=f"list_project_files failed: {e}", code="LIST_FILES_ERROR")


class GetCodeEntityInfoMCPCommand(Command):
    """Get detailed information about a code entity (class, function, method)."""

    name = "get_code_entity_info"
    version = "1.0.0"
    descr = "Get detailed information about a class, function, or method"
    category = "ast"
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
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity: 'class', 'function', or 'method'",
                    "enum": ["class", "function", "method"],
                },
                "entity_name": {
                    "type": "string",
                    "description": "Name of the entity",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to search in (absolute or relative)",
                },
                "line": {
                    "type": "integer",
                    "description": "Optional line number for disambiguation",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir", "entity_type", "entity_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        entity_type: str,
        entity_name: str,
        file_path: Optional[str] = None,
        line: Optional[int] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            db = _open_database(root_dir)
            root_path = Path(root_dir).resolve()
            proj_id = _get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(message="Project not found", code="PROJECT_NOT_FOUND")

            cmd = InternalGetEntityInfo(
                db, proj_id, entity_type, entity_name, file_path=file_path, line=line
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "get_code_entity_info failed"),
                code="GET_ENTITY_INFO_ERROR",
                details=result
            )
        except Exception as e:
            logger.exception("get_code_entity_info failed: %s", e)
            return ErrorResult(message=f"get_code_entity_info failed: {e}", code="GET_ENTITY_INFO_ERROR")

