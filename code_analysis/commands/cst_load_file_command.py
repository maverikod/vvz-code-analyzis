"""
MCP command: cst_load_file

Load Python file into CST tree and return tree_id with node metadata.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import libcst as cst
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.file_lock import file_lock
from ..core.cst_tree.tree_builder import load_file_to_tree
from ..core.cst_tree.tree_metadata import get_node_parent
from ..core.cst_tree.tree_range_finder import find_node_by_range

logger = logging.getLogger(__name__)

# Prefix for the TODO comment above a commented-out error line
_TODO_PREFIX = "TODO: The line following this one was commented out due to an error: "
_MAX_SYNTAX_FIX_ITERATIONS = 100

# Block starters that require a body (so we add pass with body indent)
_BLOCK_STARTERS = (
    "if ",
    "elif ",
    "else:",
    "try:",
    "except ",
    "except:",
    "finally:",
    "def ",
    "class ",
    "for ",
    "while ",
    "with ",
)


def _is_block_starter_line(stripped: str) -> bool:
    """True if stripped line starts a block (if/def/for/else/...)."""
    if not stripped.endswith(":"):
        return False
    key = stripped.split("(")[0].strip() if "(" in stripped else stripped
    return any(key.startswith(s.rstrip(":")) or key == s for s in _BLOCK_STARTERS)


def _indent_for_pass_after_error(lines: List[str], error_line_idx: int) -> str:
    """
    Find indent for a placeholder 'pass' so the block stays valid.
    Scans upward for a line that starts a block (if/def/else/...), returns its
    indent plus one level (4 spaces).
    """
    for i in range(error_line_idx - 1, -1, -1):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _is_block_starter_line(stripped):
            lead = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            return lead + "    "
    return "    "


def _apply_syntax_error_fix(
    lines: List[str], e: cst.ParserSyntaxError
) -> Tuple[List[str], int]:
    """
    Comment out the line reported by the parser and add TODO.
    Returns (new_lines, 1-based line number of the '# original' line in result).
    """
    line_no = e.raw_line
    err_msg = str(e).lower()
    if line_no == 1 and "dedent" in err_msg:
        candidate = None
        for i, line in enumerate(lines):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if line and not line[: len(line) - len(line.lstrip())]:
                if _is_block_starter_line(s):
                    candidate = i + 1
        if candidate is not None:
            line_no = candidate
    idx = line_no - 1
    if idx < 0 or idx >= len(lines) or not lines[idx].strip():
        raise
    raw = lines[idx]
    lead = raw[: len(raw) - len(raw.lstrip())]
    stripped = raw.strip()
    if stripped.startswith("#"):
        raise
    err_text = str(e).strip().replace("\n", " ")
    todo_line = lead + "# " + _TODO_PREFIX + err_text
    comment_line = lead + "# " + stripped
    pass_indent = _indent_for_pass_after_error(lines, idx)
    fixed = (
        lines[:idx] + [todo_line, comment_line, pass_indent + "pass"] + lines[idx + 1 :]
    )
    # 1-based line of the "# original" line in fixed
    comment_line_no = idx + 2
    return fixed, comment_line_no


class CSTLoadFileCommand(BaseMCPCommand):
    """Load file into CST tree."""

    name = "cst_load_file"
    version = "1.0.0"
    descr = "Load Python file into CST tree and return tree_id with node metadata"
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID (UUID4). Required.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target Python file path (relative to project root)",
                },
                "node_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional filter by node types (e.g., ['FunctionDef', 'ClassDef'])",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Optional maximum depth for node filtering",
                },
                "include_children": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to include children information in metadata",
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        node_types: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        include_children: bool = True,
        **kwargs,
    ) -> SuccessResult:
        t_start = time.perf_counter()
        try:
            t0 = time.perf_counter()
            database = self._open_database_from_config(auto_analyze=False)
            try:
                target = self._resolve_file_path_from_project(
                    database, project_id, file_path
                )
                if target.suffix != ".py":
                    return ErrorResult(
                        message="Target file must be a .py file",
                        code="INVALID_FILE",
                        details={"file_path": str(target)},
                    )
            finally:
                database.disconnect()
            logger.info(
                "[TIMING] command=cst_load_file step=resolve_path elapsed_sec=%.4f",
                time.perf_counter() - t0,
            )

            t0 = time.perf_counter()
            path_tmp_clean = Path(str(target) + ".tmp")
            if path_tmp_clean.exists():
                path_tmp_clean.unlink()
            logger.info(
                "[TIMING] command=cst_load_file step=cleanup_tmp elapsed_sec=%.4f",
                time.perf_counter() - t0,
            )

            tree = None
            path_tmp: Optional[Path] = None
            commented_lines_info: List[Dict[str, Any]] = []

            with file_lock(target):
                t0 = time.perf_counter()
                try:
                    tree = load_file_to_tree(
                        str(target),
                        node_types=node_types,
                        max_depth=max_depth,
                        include_children=include_children,
                    )
                except cst.ParserSyntaxError:
                    logger.info(
                        "[TIMING] command=cst_load_file step=load_tree elapsed_sec=%.4f (syntax_error)",
                        time.perf_counter() - t0,
                    )
                    t0 = time.perf_counter()
                    path_tmp = Path(str(target) + ".tmp")
                    shutil.copy2(target, path_tmp)
                    lines = path_tmp.read_text(encoding="utf-8").split("\n")
                    for _ in range(_MAX_SYNTAX_FIX_ITERATIONS):
                        try:
                            cst.parse_module("\n".join(lines))
                            break
                        except cst.ParserSyntaxError as e:
                            lines, comment_line_no = _apply_syntax_error_fix(lines, e)
                            commented_lines_info.append(
                                {
                                    "line": comment_line_no,
                                    "error": str(e).strip(),
                                }
                            )
                    else:
                        raise ValueError(
                            f"Syntax fix did not converge after "
                            f"{_MAX_SYNTAX_FIX_ITERATIONS} iterations"
                        )
                    path_tmp.write_text("\n".join(lines), encoding="utf-8")
                    logger.info(
                        "[TIMING] command=cst_load_file step=syntax_fix_loop elapsed_sec=%.4f",
                        time.perf_counter() - t0,
                    )
                    t0 = time.perf_counter()
                    tree = load_file_to_tree(
                        str(path_tmp),
                        node_types=node_types,
                        max_depth=max_depth,
                        include_children=include_children,
                    )
                    logger.info(
                        "[TIMING] command=cst_load_file step=load_tree_from_tmp elapsed_sec=%.4f",
                        time.perf_counter() - t0,
                    )
                    t0 = time.perf_counter()
                    for info in commented_lines_info:
                        line_no = info["line"]
                        node = find_node_by_range(
                            tree.tree_id,
                            line_no,
                            line_no,
                            prefer_exact=False,
                        )
                        parent = None
                        if node:
                            parent_meta = get_node_parent(tree.tree_id, node.node_id)
                            if parent_meta:
                                parent = parent_meta.to_dict()
                        info["parent_node"] = parent
                    logger.info(
                        "[TIMING] command=cst_load_file step=parent_nodes elapsed_sec=%.4f",
                        time.perf_counter() - t0,
                    )
                else:
                    logger.info(
                        "[TIMING] command=cst_load_file step=load_tree elapsed_sec=%.4f",
                        time.perf_counter() - t0,
                    )

                t0 = time.perf_counter()
                nodes = [meta.to_dict() for meta in tree.metadata_map.values()]
                logger.info(
                    "[TIMING] command=cst_load_file step=to_dict elapsed_sec=%.4f nodes=%s",
                    time.perf_counter() - t0,
                    len(nodes),
                )

                data: Dict[str, Any] = {
                    "success": True,
                    "tree_id": tree.tree_id,
                    "file_path": str(target),
                    "nodes": nodes,
                    "total_nodes": len(nodes),
                }
                if commented_lines_info:
                    data["syntax_errors_fixed"] = True
                    data["commented_lines"] = commented_lines_info
                    data["temp_file"] = str(path_tmp) if path_tmp else None

                logger.info(
                    "[TIMING] command=cst_load_file total_elapsed_sec=%.4f",
                    time.perf_counter() - t_start,
                )
                return SuccessResult(data=data)

        except FileNotFoundError as e:
            return ErrorResult(
                message=f"File not found: {e}",
                code="FILE_NOT_FOUND",
                details={"file_path": file_path},
            )
        except ValueError as e:
            return ErrorResult(
                message=f"Invalid file: {e}",
                code="INVALID_FILE",
                details={"file_path": file_path},
            )
        except Exception as e:
            logger.exception("cst_load_file failed: %s", e)
            return ErrorResult(
                message=f"cst_load_file failed: {e}", code="CST_LOAD_ERROR"
            )

    @classmethod
    def metadata(cls: type["CSTLoadFileCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The cst_load_file command loads a Python file into a CST tree and stores it in memory. "
                "It returns a tree_id that can be used with other CST tree commands (cst_modify_tree, "
                "cst_save_tree, cst_find_node). The full CST tree is stored on the server, and only "
                "node metadata is returned to the client.\n\n"
                "Operation flow:\n"
                "1. Gets project from database using project_id\n"
                "2. Validates project is linked to watch directory\n"
                "3. Gets watch directory path from database\n"
                "4. Forms absolute path: watch_dir_path / project_name / file_path\n"
                "5. Validates file is a .py file\n"
                "6. Validates file exists\n"
                "7. Reads file source code\n"
                "8. Parses source using LibCST\n"
                "9. Builds node index and metadata\n"
                "10. Stores tree in memory with tree_id\n"
                "11. Returns tree_id and node metadata\n\n"
                "Node Metadata:\n"
                "Each node includes:\n"
                "- node_id: Stable identifier for operations\n"
                "- type: LibCST node type (FunctionDef, ClassDef, etc.)\n"
                "- kind: Node kind (function, class, method, stmt, smallstmt, etc.)\n"
                "- name: Node name (if applicable)\n"
                "- qualname: Qualified name (if applicable)\n"
                "- start_line, start_col, end_line, end_col: Position\n"
                "- children_count: Number of children\n"
                "- children_ids: List of child node IDs (if include_children=True)\n"
                "- parent_id: Parent node ID (if applicable)\n\n"
                "Filters:\n"
                "- node_types: Filter by node types (e.g., ['FunctionDef', 'ClassDef'])\n"
                "- max_depth: Limit depth of nodes returned\n"
                "- include_children: Whether to include children information\n\n"
                "Use cases:\n"
                "- Load file for modification operations\n"
                "- Analyze code structure\n"
                "- Find specific nodes for refactoring\n"
                "- Prepare for batch operations\n\n"
                "Important notes:\n"
                "- Tree is stored in memory on the server\n"
                "- Tree persists until explicitly removed or server restarts\n"
                "- Use tree_id with other CST commands\n"
                "- Filters reduce returned metadata, but full tree is still stored\n\n"
                "When the file had syntax errors on load:\n"
                "- The server comments out the error lines and adds a placeholder 'pass'\n"
                "- The response includes syntax_errors_fixed: true, commented_lines: [{ line, error, parent_node }], and optionally temp_file\n"
                "- Each commented_lines entry has parent_node (dict with node_id) for the block where the error was found; use it to locate the parent (e.g. function/class)"
            ),
            "parameters": {
                "project_id": {
                    "description": "Project ID (UUID4). Project must be linked to a watch directory.",
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": "Target Python file path (relative to project root). Absolute path is formed as: watch_dir_path / project_name / file_path",
                    "type": "string",
                    "required": True,
                },
                "root_dir": {
                    "description": "Server root directory (optional, for database access). If not provided, will be resolved from config.",
                    "type": "string",
                    "required": False,
                },
                "node_types": {
                    "description": "Optional filter by node types. Only nodes matching these types will be included in metadata.",
                    "type": "array",
                    "items": {"type": "string"},
                    "required": False,
                    "examples": [["FunctionDef", "ClassDef"], ["If", "For", "Try"]],
                },
                "max_depth": {
                    "description": "Optional maximum depth for node filtering. Nodes deeper than this will be excluded.",
                    "type": "integer",
                    "required": False,
                    "examples": [1, 2, 3],
                },
                "include_children": {
                    "description": "Whether to include children information in metadata. Default is True.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
            },
            "return_value": {
                "success": {
                    "description": "File loaded successfully",
                    "data": {
                        "success": "Always True on success",
                        "tree_id": "Tree ID for use with other CST commands",
                        "file_path": "Path to loaded file",
                        "nodes": "List of node metadata dictionaries",
                        "total_nodes": "Total number of nodes returned",
                        "syntax_errors_fixed": "Optional. True when file had syntax errors on load; error lines were commented out and a placeholder pass was added.",
                        "commented_lines": "Optional. When syntax_errors_fixed is true: list of { line (1-based), error (message), parent_node (dict with node_id, or null) } for each commented-out error line. parent_node identifies the block (e.g. function/class) where the error was found.",
                        "temp_file": "Optional. When syntax_errors_fixed is true: path to the .tmp file used for the fixed content (for debugging).",
                    },
                    "example": {
                        "success": True,
                        "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "file_path": "/home/user/projects/my_project/src/main.py",
                        "nodes": [
                            {
                                "node_id": "function:main:FunctionDef:10:0-25:0",
                                "type": "FunctionDef",
                                "kind": "function",
                                "name": "main",
                                "qualname": "main",
                                "start_line": 10,
                                "start_col": 0,
                                "end_line": 25,
                                "end_col": 0,
                                "children_count": 3,
                                "children_ids": [
                                    "stmt:If:12:4-20:0",
                                    "smallstmt:Return:22:4-22:12",
                                ],
                            }
                        ],
                        "total_nodes": 42,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., FILE_NOT_FOUND, INVALID_FILE, CST_LOAD_ERROR)",
                    "message": "Human-readable error message",
                    "details": "Additional error information (if available)",
                },
            },
            "usage_examples": [
                {
                    "description": "Load file without filters",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Loads entire file into CST tree. Returns all nodes with full metadata. "
                        "Absolute path is formed as: watch_dir_path / project_name / src/main.py. "
                        "Use this when you need to work with all nodes in the file."
                    ),
                },
                {
                    "description": "Load only functions and classes",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/models.py",
                        "node_types": ["FunctionDef", "ClassDef"],
                    },
                    "explanation": (
                        "Loads file but returns metadata only for functions and classes. "
                        "Useful when you only need to work with top-level definitions. "
                        "Full tree is still stored, but metadata is filtered."
                    ),
                },
                {
                    "description": "Load with depth limit",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                        "max_depth": 2,
                    },
                    "explanation": (
                        "Loads file but returns nodes only up to depth 2. "
                        "Useful for analyzing top-level structure without deep nesting details."
                    ),
                },
                {
                    "description": "Load without children information",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/utils.py",
                        "include_children": False,
                    },
                    "explanation": (
                        "Loads file but excludes children_ids from metadata. "
                        "Reduces response size when children information is not needed."
                    ),
                },
                {
                    "description": "Load specific statement types",
                    "command": {
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "file_path": "src/main.py",
                        "node_types": ["If", "For", "Try", "With"],
                    },
                    "explanation": (
                        "Loads file but returns only control flow statements (if, for, try, with). "
                        "Useful for analyzing control flow patterns."
                    ),
                },
            ],
            "error_cases": {
                "FILE_NOT_FOUND": {
                    "description": "File does not exist",
                    "message": "File not found: {file_path}",
                    "solution": "Verify file_path is correct and file exists",
                },
                "INVALID_FILE": {
                    "description": "File is not a Python file",
                    "message": "File must be a .py file: {file_path}",
                    "solution": "Ensure file_path points to a .py file",
                },
                "CST_LOAD_ERROR": {
                    "description": "Error during file loading",
                    "examples": [
                        {
                            "case": "Syntax error in file",
                            "message": "cst_load_file failed: SyntaxError",
                            "solution": (
                                "Fix syntax errors in the file. "
                                "LibCST requires valid Python syntax to parse."
                            ),
                        },
                        {
                            "case": "File encoding error",
                            "message": "cst_load_file failed: UnicodeDecodeError",
                            "solution": (
                                "Ensure file is UTF-8 encoded. "
                                "Check file encoding and convert if needed."
                            ),
                        },
                    ],
                },
            },
            "best_practices": [
                "Always provide project_id - it is required and used to form absolute path",
                "Ensure project is linked to watch directory before using this command",
                "Use relative file_path from project root (e.g., 'src/main.py' not '/absolute/path')",
                "Use node_types filter to reduce metadata size when only specific types are needed",
                "Use max_depth to limit analysis scope",
                "Set include_children=False if children information is not needed",
                "Save tree_id for use with cst_modify_tree and cst_save_tree",
                "Tree persists in memory until server restart or explicit removal",
            ],
        }
