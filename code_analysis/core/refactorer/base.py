"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import shutil
import tokenize
import io
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class BaseRefactorer:
    """Base class with common functionality."""

    def __init__(self, file_path: Path) -> None:
        """Initialize class splitter."""
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        self.backup_path: Optional[Path] = None
        self.original_content: str = ""
        self.tree: Optional[ast.Module] = None

    def _extract_method_code(self, method_node: Any, indent: str) -> str:
        """
        Extract method code as string with proper indentation using AST unparse.

        Comments are preserved as string expressions in AST and converted back
        to comments in the output. Docstrings are also preserved.

        Args:
            method_node: AST node of the method (FunctionDef or AsyncFunctionDef)
            indent: Base indentation string (e.g., "    " for 4 spaces)

        Returns:
            Method code as string with proper indentation
        """
        try:
            unparsed = ast.unparse(method_node)
            lines = unparsed.split("\n")
            adjusted_lines = []
            for line in lines:
                stripped = line.strip()
                if (
                    stripped.startswith('"') or stripped.startswith("'")
                ) and "#" in stripped:
                    try:
                        if stripped.startswith('"""') or stripped.startswith("'''"):
                            adjusted_lines.append(line)
                        elif stripped.startswith('"') and stripped.endswith('"'):
                            comment = stripped[1:-1]
                            if comment.startswith("#"):
                                line_indent = len(line) - len(line.lstrip())
                                adjusted_lines.append(" " * line_indent + comment)
                            else:
                                adjusted_lines.append(line)
                        elif stripped.startswith("'") and stripped.endswith("'"):
                            comment = stripped[1:-1]
                            if comment.startswith("#"):
                                line_indent = len(line) - len(line.lstrip())
                                adjusted_lines.append(" " * line_indent + comment)
                            else:
                                adjusted_lines.append(line)
                        else:
                            adjusted_lines.append(line)
                    except Exception:
                        adjusted_lines.append(line)
                else:
                    adjusted_lines.append(line)
            if not adjusted_lines:
                return ""
            first_line = adjusted_lines[0]
            base_indent = len(first_line) - len(first_line.lstrip())
            final_lines = []
            for line in adjusted_lines:
                if line.strip():
                    line_without_base = (
                        line[base_indent:] if len(line) > base_indent else line.lstrip()
                    )
                    final_lines.append(indent + line_without_base)
                else:
                    final_lines.append("")
            result = "\n".join(final_lines)
            return result if result.strip() else ""
        except Exception as e:
            logger.warning(
                f"ast.unparse() failed, falling back to string extraction: {e}"
            )
            if not hasattr(method_node, "lineno"):
                # The node was likely synthesized (no source positions). Try to unparse
                # it after adding missing locations, then indent it for embedding.
                try:
                    fixed = ast.fix_missing_locations(method_node)
                    code = ast.unparse(fixed)
                    indented_lines: list[str] = []
                    for line in code.splitlines():
                        indented_lines.append(indent + line if line.strip() else "")
                    return "\n".join(indented_lines)
                except Exception:
                    return ""
            lines = self.original_content.split("\n")
            method_start_line = method_node.lineno - 1
            if hasattr(method_node, "end_lineno") and method_node.end_lineno:
                method_end = method_node.end_lineno
            else:
                method_indent = len(lines[method_start_line]) - len(
                    lines[method_start_line].lstrip()
                )
                method_end = method_start_line + 1
                for i in range(method_start_line + 1, len(lines)):
                    line = lines[i]
                    if line.strip() and (not line.strip().startswith("#")):
                        line_indent = len(line) - len(line.lstrip())
                        if line_indent <= method_indent:
                            method_end = i
                            break
                    method_end = i + 1
            method_lines = lines[method_start_line:method_end]
            if method_lines:
                original_indent = 0
                for line in method_lines:
                    if line.strip():
                        original_indent = len(line) - len(line.lstrip())
                        break
                adjusted_lines = []
                for line in method_lines:
                    if line.strip():
                        current_indent = len(line) - len(line.lstrip())
                        indent_diff = current_indent - original_indent
                        new_indent = indent + " " * indent_diff
                        adjusted_lines.append(new_indent + line.lstrip())
                    else:
                        adjusted_lines.append("")
                result = "\n".join(adjusted_lines)
                if result.strip():
                    return result
            return ""

    def _find_class_end(self, class_node: ast.ClassDef, lines: List[str]) -> int:
        """Find the end line of a class definition."""
        if class_node.body:
            last_stmt = class_node.body[-1]
            if hasattr(last_stmt, "end_lineno") and last_stmt.end_lineno:
                return last_stmt.end_lineno
            else:
                class_indent = len(lines[class_node.lineno - 1]) - len(
                    lines[class_node.lineno - 1].lstrip()
                )
                for i in range(last_stmt.lineno, len(lines)):
                    line = lines[i]
                    if line.strip() and (not line.strip().startswith("#")):
                        indent = len(line) - len(line.lstrip())
                        if indent <= class_indent:
                            return i
                return len(lines)
        return class_node.lineno

    def create_backup(self) -> Path:
        """Create backup copy of the file."""
        backup_dir = self.file_path.parent / ".code_mapper_backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = int(Path(self.file_path).stat().st_mtime)
        backup_path = backup_dir / f"{self.file_path.stem}_{timestamp}.py.backup"
        shutil.copy2(self.file_path, backup_path)
        self.backup_path = backup_path
        logger.info(f"Backup created: {backup_path}")
        return backup_path

    def extract_init_properties(self, class_node: ast.ClassDef) -> List[str]:
        """Extract properties initialized in __init__."""
        properties = []
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in item.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    properties.append(target.attr)
                    elif isinstance(stmt, ast.AnnAssign):
                        if isinstance(stmt.target, ast.Attribute):
                            if (
                                isinstance(stmt.target.value, ast.Name)
                                and stmt.target.value.id == "self"
                            ):
                                properties.append(stmt.target.attr)
        return properties

    def find_class(self, class_name: str) -> Optional[ast.ClassDef]:
        """Find class definition in AST."""
        if not self.tree:
            return None
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                return node
        return None

    def _parse_with_comments(self, source: str) -> ast.Module:
        """
        Parse Python code and preserve comments as string expressions in AST.

        Comments are added as ast.Expr(ast.Constant(value="# comment")) nodes
        before the statements they precede.

        Args:
            source: Python source code string

        Returns:
            AST module with comments preserved as string expressions
        """
        tree = ast.parse(source, filename=str(self.file_path))
        comments_map: Dict[int, List[Tuple[int, str]]] = {}
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    line_num = token.start[0]
                    col = token.start[1]
                    comment_text = token.string.strip()
                    if line_num not in comments_map:
                        comments_map[line_num] = []
                    comments_map[line_num].append((col, comment_text))
        except Exception as e:
            logger.warning(f"Failed to extract comments: {e}")
            return tree

        def add_comments_to_node(node: ast.AST, parent_body: List[ast.stmt]) -> None:
            """Recursively add comments to AST nodes."""
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                node_line = node.lineno
                if node_line in comments_map:
                    try:
                        node_idx = parent_body.index(node)
                    except ValueError:
                        return
                    for col, comment_text in sorted(
                        comments_map[node_line], reverse=True
                    ):
                        if col < node.col_offset:
                            comment_node = ast.Expr(ast.Constant(value=comment_text))
                            comment_node.lineno = node_line
                            comment_node.col_offset = col
                            parent_body.insert(node_idx, comment_node)
                    del comments_map[node_line]
                if hasattr(node, "body") and isinstance(node.body, list):
                    for i, child in enumerate(node.body[:]):
                        add_comments_to_node(child, node.body)
            elif isinstance(node, ast.stmt):
                node_line = node.lineno
                if node_line in comments_map:
                    try:
                        node_idx = parent_body.index(node)
                    except ValueError:
                        return
                    for col, comment_text in sorted(
                        comments_map[node_line], reverse=True
                    ):
                        if col < getattr(node, "col_offset", 0):
                            comment_node = ast.Expr(ast.Constant(value=comment_text))
                            comment_node.lineno = node_line
                            comment_node.col_offset = col
                            parent_body.insert(node_idx, comment_node)
                    del comments_map[node_line]

        for node in tree.body:
            add_comments_to_node(node, tree.body)
        return tree

    def load_file(self) -> None:
        """Load and parse file content with comments preserved."""
        with open(self.file_path, "r", encoding="utf-8") as f:
            self.original_content = f.read()
        self.tree = self._parse_with_comments(self.original_content)

    def restore_backup(self) -> None:
        """Restore file from backup."""
        if self.backup_path and self.backup_path.exists():
            shutil.copy2(self.backup_path, self.file_path)
            logger.info(f"File restored from backup: {self.backup_path}")

    def validate_imports(self) -> tuple[bool, Optional[str]]:
        """Try to import the modified module."""
        from .validators import validate_imports as validate_imports_func

        return validate_imports_func(self.file_path)

    def validate_python_syntax(self) -> tuple[bool, Optional[str]]:
        """Validate Python syntax of modified file."""
        from .validators import validate_python_syntax as validate_syntax_func

        return validate_syntax_func(self.file_path)
