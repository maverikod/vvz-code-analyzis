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
from .list_code_entities import ListCodeEntitiesCommand as InternalListEntities
from .get_imports import GetImportsCommand as InternalGetImports
from .find_dependencies import FindDependenciesCommand as InternalFindDependencies
from .get_class_hierarchy import GetClassHierarchyCommand as InternalGetClassHierarchy
from .find_usages import FindUsagesCommand as InternalFindUsages

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


class ListCodeEntitiesMCPCommand(Command):
    """List code entities (classes, functions, methods) in a file or project."""

    name = "list_code_entities"
    version = "1.0.0"
    descr = "List classes, functions, or methods in a file or project"
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
                    "description": "Type of entity: 'class', 'function', 'method', or null for all",
                    "enum": ["class", "function", "method"],
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to filter by (absolute or relative)",
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
        entity_type: Optional[str] = None,
        file_path: Optional[str] = None,
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

            cmd = InternalListEntities(
                db, proj_id, entity_type=entity_type, file_path=file_path, limit=limit, offset=offset
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "list_code_entities failed"),
                code="LIST_ENTITIES_ERROR",
                details=result
            )
        except Exception as e:
            logger.exception("list_code_entities failed: %s", e)
            return ErrorResult(message=f"list_code_entities failed: {e}", code="LIST_ENTITIES_ERROR")


class GetImportsMCPCommand(Command):
    """Get imports information from files or project."""

    name = "get_imports"
    version = "1.0.0"
    descr = "Get list of imports in a file or project with filtering options"
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
                    "description": "Optional file path to filter by (absolute or relative)",
                },
                "import_type": {
                    "type": "string",
                    "description": "Type of import: 'import' or 'import_from'",
                    "enum": ["import", "import_from"],
                },
                "module_name": {
                    "type": "string",
                    "description": "Optional module name to filter by",
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
        file_path: Optional[str] = None,
        import_type: Optional[str] = None,
        module_name: Optional[str] = None,
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

            cmd = InternalGetImports(
                db,
                proj_id,
                file_path=file_path,
                import_type=import_type,
                module_name=module_name,
                limit=limit,
                offset=offset,
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "get_imports failed"),
                code="GET_IMPORTS_ERROR",
                details=result
            )
        except Exception as e:
            logger.exception("get_imports failed: %s", e)
            return ErrorResult(message=f"get_imports failed: {e}", code="GET_IMPORTS_ERROR")


class FindDependenciesMCPCommand(Command):
    """Find dependencies - where classes, functions, or modules are used."""

    name = "find_dependencies"
    version = "1.0.0"
    descr = "Find where a class, function, method, or module is used in the project"
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
                "entity_name": {
                    "type": "string",
                    "description": "Name of entity to find dependencies for",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity: 'class', 'function', 'method', 'module', or null for all",
                    "enum": ["class", "function", "method", "module"],
                },
                "target_class": {
                    "type": "string",
                    "description": "Optional class name for methods",
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
            "required": ["root_dir", "entity_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        entity_name: str,
        entity_type: Optional[str] = None,
        target_class: Optional[str] = None,
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

            cmd = InternalFindDependencies(
                db,
                proj_id,
                entity_name=entity_name,
                entity_type=entity_type,
                target_class=target_class,
                limit=limit,
                offset=offset,
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "find_dependencies failed"),
                code="FIND_DEPENDENCIES_ERROR",
                details=result
            )
        except Exception as e:
            logger.exception("find_dependencies failed: %s", e)
            return ErrorResult(message=f"find_dependencies failed: {e}", code="FIND_DEPENDENCIES_ERROR")


class GetClassHierarchyMCPCommand(Command):
    """Get class hierarchy (inheritance tree)."""

    name = "get_class_hierarchy"
    version = "1.0.0"
    descr = "Get class inheritance hierarchy for a specific class or all classes"
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
                "class_name": {
                    "type": "string",
                    "description": "Optional class name to get hierarchy for (if null, returns all hierarchies)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to filter by (absolute or relative)",
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
        class_name: Optional[str] = None,
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

            cmd = InternalGetClassHierarchy(
                db, proj_id, class_name=class_name, file_path=file_path
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "get_class_hierarchy failed"),
                code="GET_CLASS_HIERARCHY_ERROR",
                details=result
            )
        except Exception as e:
            logger.exception("get_class_hierarchy failed: %s", e)
            return ErrorResult(message=f"get_class_hierarchy failed: {e}", code="GET_CLASS_HIERARCHY_ERROR")


class FindUsagesMCPCommand(Command):
    """Find usages of methods, properties, classes, or functions."""

    name = "find_usages"
    version = "1.0.0"
    descr = "Find where a method, property, class, or function is used in the project"
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
                "target_name": {
                    "type": "string",
                    "description": "Name of target to find usages for",
                },
                "target_type": {
                    "type": "string",
                    "description": "Type of target: 'method', 'property', 'class', 'function', or null for all",
                    "enum": ["method", "property", "class", "function"],
                },
                "target_class": {
                    "type": "string",
                    "description": "Optional class name for methods/properties",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to filter by (where usage occurs)",
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
            "required": ["root_dir", "target_name"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        target_name: str,
        target_type: Optional[str] = None,
        target_class: Optional[str] = None,
        file_path: Optional[str] = None,
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

            cmd = InternalFindUsages(
                db,
                proj_id,
                target_name=target_name,
                target_type=target_type,
                target_class=target_class,
                file_path=file_path,
                limit=limit,
                offset=offset,
            )
            result = await cmd.execute()
            db.close()

            if result.get("success"):
                return SuccessResult(data=result)
            return ErrorResult(
                message=result.get("message", "find_usages failed"),
                code="FIND_USAGES_ERROR",
                details=result
            )
        except Exception as e:
            logger.exception("find_usages failed: %s", e)
            return ErrorResult(message=f"find_usages failed: {e}", code="FIND_USAGES_ERROR")

