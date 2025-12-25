"""
Code analyzer for the code mapper.

This module contains the core analysis functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import json
import hashlib
from pathlib import Path
import logging
from typing import Dict, List, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .database import CodeDatabase  # noqa: F401
    from .svo_client_manager import SVOClientManager  # noqa: F401
    from .faiss_manager import FaissIndexManager  # noqa: F401

from .usage_analyzer import UsageAnalyzer

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    """Core code analyzer functionality."""

    def __init__(
        self,
        root_dir: str = ".",
        output_dir: str = "code_analysis",
        max_lines: int = 400,
        issue_detector=None,
        database=None,
        svo_client_manager: Optional["SVOClientManager"] = None,
        faiss_manager: Optional["FaissIndexManager"] = None,
    ):
        """Initialize code analyzer."""
        self.root_dir = Path(root_dir)
        self.output_dir = Path(output_dir)
        self.max_lines = max_lines
        self.issue_detector = issue_detector
        self.database = database
        self.svo_client_manager = svo_client_manager
        self.faiss_manager = faiss_manager
        self.usage_analyzer = UsageAnalyzer(database) if database else None

        # Initialize docstring chunker if SVO client manager provided
        self.docstring_chunker = None
        if database and svo_client_manager:
            from .docstring_chunker import DocstringChunker

            # Get min_chunk_length from config if available
            min_chunk_length = 30  # default
            if hasattr(svo_client_manager, "config") and svo_client_manager.config:
                min_chunk_length = getattr(
                    svo_client_manager.config, "min_chunk_length", 30
                )
            self.docstring_chunker = DocstringChunker(
                database=database,
                svo_client_manager=svo_client_manager,
                faiss_manager=faiss_manager,
                min_chunk_length=min_chunk_length,
            )

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(exist_ok=True)

        # Keep code_map for backward compatibility (YAML mode)
        self.code_map: Dict[str, Any] = {
            "files": {},
            "classes": {},
            "functions": {},
            "imports": {},
            "dependencies": {},
        }
        # Issues tracking (for backward compatibility)
        self.issues: Dict[str, List[Any]] = {
            "methods_with_pass": [],
            "not_implemented_in_non_abstract": [],
            "methods_without_docstrings": [],
            "files_without_docstrings": [],
            "classes_without_docstrings": [],
            "files_too_large": [],
            "any_type_usage": [],
            "generic_exception_usage": [],
            "imports_in_middle": [],
            "invalid_imports": [],
        }

    async def analyze_file(self, file_path: Path, force: bool = False) -> None:
        """
        Analyze a single Python file.

        Args:
            file_path: Path to Python file
            force: If True, process file regardless of modification time
        """
        logger.info(f"📄 Analyzing file: {file_path}")
        try:
            file_path_str = str(file_path)
            file_stat = file_path.stat()
            last_modified = file_stat.st_mtime

            logger.debug(
                f"   File size: {file_stat.st_size} bytes, mtime: {last_modified}"
            )
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            logger.debug(
                f"   Content length: {len(content)} chars, lines: {len(content.splitlines())}"
            )
            tree = ast.parse(content)
            logger.debug("   AST parsed successfully")

            # Check file size
            lines = content.split("\n")
            line_count = len(lines)
            has_docstring = self._has_file_docstring(tree)

            # Save file to database if using SQLite
            file_id = None
            project_id = None
            if self.database:
                # Get or create project
                project_id = self.database.get_or_create_project(
                    str(self.root_dir), name=self.root_dir.name
                )
                file_id = self.database.add_file(
                    file_path_str, line_count, last_modified, has_docstring, project_id
                )

            # Check file size
            if line_count > self.max_lines:
                issue_data = {
                    "file": file_path_str,
                    "lines": line_count,
                    "limit": self.max_lines,
                    "exceeds_limit": line_count - self.max_lines,
                }
                self.issues["files_too_large"].append(issue_data)

                if self.database and file_id:
                    self.database.add_issue(
                        "files_too_large",
                        f"File exceeds line limit: {line_count} > {self.max_lines}",
                        line=None,
                        file_id=file_id,
                        metadata=issue_data,
                    )

            # Check for file docstring
            if not has_docstring:
                self.issues["files_without_docstrings"].append(file_path_str)
                if self.database and file_id:
                    self.database.add_issue(
                        "files_without_docstrings",
                        "File missing docstring",
                        line=None,
                        file_id=file_id,
                    )

            # Analyze AST
            logger.debug("   Analyzing AST structure...")
            self._analyze_ast(tree, file_path, file_id)
            logger.debug("   AST analysis completed")

            # Save AST tree to database
            if self.database and file_id:
                logger.debug("   Saving AST tree to database...")
                ast_saved = await self._save_ast_tree(
                    tree, file_id, project_id, last_modified, force=False
                )
                if ast_saved:
                    logger.debug("   ✅ AST tree saved to database")
                else:
                    logger.debug("   ⏭️  AST tree skipped (up to date)")

            # Analyze usages (method calls, attribute accesses)
            if self.usage_analyzer and file_id:
                logger.debug("   Analyzing usages...")
                self.usage_analyzer.analyze_file(file_path, file_id)

            # Process docstrings and comments: chunk and embed
            if self.docstring_chunker and file_id and project_id:
                logger.info("   🔍 Processing docstrings and comments for chunking...")
                await self.docstring_chunker.process_file(
                    file_path=file_path,
                    file_id=file_id,
                    project_id=project_id,
                    tree=tree,
                    file_content=content,
                )
                logger.debug("   ✅ Docstring chunking completed")
            else:
                logger.debug("   ⏭️  Docstring chunking skipped (chunker not available)")

            logger.info(f"✅ File analysis completed: {file_path}")

        except (OSError, IOError, ValueError, SyntaxError, UnicodeDecodeError) as e:
            logger.error(f"Error analyzing file {file_path}: {e}")

    def _has_file_docstring(self, tree: ast.Module) -> bool:
        """Check if file has a docstring."""
        if not tree.body:
            return False

        first_node = tree.body[0]
        return (
            isinstance(first_node, ast.Expr)
            and isinstance(first_node.value, ast.Constant)
            and isinstance(first_node.value.value, str)
        )

    def _analyze_ast(
        self, tree: ast.Module, file_path: Path, file_id: Optional[int] = None
    ) -> None:
        """Analyze AST nodes."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self._analyze_class(node, file_path, file_id)
            elif isinstance(node, ast.FunctionDef):
                # Only analyze top-level functions (not methods)
                # Methods are handled in _analyze_class
                # Skip methods here - they will be handled in _analyze_class
                pass
            elif isinstance(node, ast.Import):
                self._analyze_import(node, file_path, file_id)
            elif isinstance(node, ast.ImportFrom):
                self._analyze_import_from(node, file_path, file_id)

        # Second pass: analyze classes and top-level functions
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                self._analyze_class(node, file_path, file_id)
            elif isinstance(node, ast.FunctionDef):
                self._analyze_function(node, file_path, file_id)

    def _analyze_class(
        self, node: ast.ClassDef, file_path: Path, file_id: Optional[int] = None
    ) -> None:
        """Analyze class definition."""
        class_name = node.name
        file_path_str = str(file_path)
        bases = [
            base.id if isinstance(base, ast.Name) else str(base) for base in node.bases
        ]
        docstring = ast.get_docstring(node)

        class_info: Dict[str, Any] = {
            "name": class_name,
            "file": file_path_str,
            "line": node.lineno,
            "bases": bases,
            "methods": [],
            "docstring": docstring,
        }

        # Save to database
        class_id = None
        if self.database and file_id:
            class_id = self.database.add_class(
                file_id, class_name, node.lineno, docstring, bases
            )

            # Save class content for full-text search
            try:
                class_code = (
                    ast.get_source_segment(self._get_file_content(file_path), node)
                    or ""
                )
                self.database.add_code_content(
                    file_id=file_id,
                    entity_type="class",
                    entity_name=class_name,
                    content=class_code,
                    docstring=docstring,
                    entity_id=class_id,
                )
            except Exception as e:
                logger.debug(f"Error saving class content: {e}")

        # Check for class docstring
        if not docstring:
            issue_data = {
                "class": class_name,
                "file": file_path_str,
                "line": node.lineno,
            }
            self.issues["classes_without_docstrings"].append(issue_data)
            if self.database and class_id:
                self.database.add_issue(
                    "classes_without_docstrings",
                    f"Class '{class_name}' missing docstring",
                    line=node.lineno,
                    file_id=file_id,
                    class_id=class_id,
                    metadata=issue_data,
                )

        # Analyze methods
        for method in node.body:
            if isinstance(method, ast.FunctionDef):
                self._analyze_method(method, file_path, class_name, class_id, file_id)
                class_info["methods"].append(method.name)

        self.code_map["classes"][f"{file_path}:{class_name}"] = class_info

    def _analyze_function(
        self, node: ast.FunctionDef, file_path: Path, file_id: Optional[int] = None
    ) -> None:
        """Analyze function definition."""
        file_path_str = str(file_path)
        args = [arg.arg for arg in node.args.args]
        docstring = ast.get_docstring(node)

        func_info = {
            "name": node.name,
            "file": file_path_str,
            "line": node.lineno,
            "args": args,
            "docstring": docstring,
        }

        # Save to database
        function_id = None
        if self.database and file_id:
            function_id = self.database.add_function(
                file_id, node.name, node.lineno, args, docstring
            )

            # Save function content for full-text search
            try:
                function_code = (
                    ast.get_source_segment(self._get_file_content(file_path), node)
                    or ""
                )
                self.database.add_code_content(
                    file_id=file_id,
                    entity_type="function",
                    entity_name=node.name,
                    content=function_code,
                    docstring=docstring,
                    entity_id=function_id,
                )
            except Exception as e:
                logger.debug(f"Error saving function content: {e}")

        # Check for function docstring
        if not docstring:
            issue_data = {
                "class": None,
                "file": file_path_str,
                "line": node.lineno,
                "method": node.name,
            }
            self.issues["methods_without_docstrings"].append(issue_data)
            if self.database and function_id:
                self.database.add_issue(
                    "methods_without_docstrings",
                    f"Function '{node.name}' missing docstring",
                    line=node.lineno,
                    file_id=file_id,
                    function_id=function_id,
                    metadata=issue_data,
                )

        self.code_map["functions"][f"{file_path}:{node.name}"] = func_info

    def _analyze_method(
        self,
        node: ast.FunctionDef,
        file_path: Path,
        class_name: str,
        class_id: Optional[int] = None,
        file_id: Optional[int] = None,
    ) -> None:
        """Analyze method definition."""
        file_path_str = str(file_path)
        args = [arg.arg for arg in node.args.args]
        docstring = ast.get_docstring(node)
        is_abstract = self._is_abstract_method(node)
        has_pass = self._has_pass_statement(node)
        has_not_implemented = self._has_not_implemented_error(node)

        # Save to database
        method_id = None
        if self.database and class_id:
            method_id = self.database.add_method(
                class_id,
                node.name,
                node.lineno,
                args,
                docstring,
                is_abstract,
                has_pass,
                has_not_implemented,
            )

            # Save method content for full-text search
            try:
                method_code = (
                    ast.get_source_segment(self._get_file_content(file_path), node)
                    or ""
                )
                file_id = self.database.get_file_id(str(file_path))
                if file_id:
                    self.database.add_code_content(
                        file_id=file_id,
                        entity_type="method",
                        entity_name=f"{class_name}.{node.name}",
                        content=method_code,
                        docstring=docstring,
                        entity_id=method_id,
                    )
            except Exception as e:
                logger.debug(f"Error saving method content: {e}")

        # Check for method docstring
        if not docstring:
            issue_data = {
                "class": class_name,
                "file": file_path_str,
                "line": node.lineno,
                "method": node.name,
            }
            self.issues["methods_without_docstrings"].append(issue_data)
            if self.database and method_id:
                self.database.add_issue(
                    "methods_without_docstrings",
                    f"Method '{class_name}.{node.name}' missing docstring",
                    line=node.lineno,
                    file_id=file_id,
                    class_id=class_id,
                    method_id=method_id,
                    metadata=issue_data,
                )

        # Check for pass statements
        if has_pass:
            issue_data = {
                "class": class_name,
                "file": file_path_str,
                "line": node.lineno,
                "method": node.name,
            }
            self.issues["methods_with_pass"].append(issue_data)
            if self.database and method_id:
                self.database.add_issue(
                    "methods_with_pass",
                    f"Method '{class_name}.{node.name}' contains only pass statement",
                    line=node.lineno,
                    file_id=file_id,
                    class_id=class_id,
                    method_id=method_id,
                    metadata=issue_data,
                )

        # Check for NotImplementedError in non-abstract methods
        if has_not_implemented and not is_abstract:
            issue_data = {
                "class": class_name,
                "file": file_path_str,
                "line": node.lineno,
                "method": node.name,
            }
            self.issues["not_implemented_in_non_abstract"].append(issue_data)
            if self.database and method_id:
                self.database.add_issue(
                    "not_implemented_in_non_abstract",
                    (
                        f"Method '{class_name}.{node.name}' "
                        "raises NotImplementedError but is not abstract"
                    ),
                    line=node.lineno,
                    file_id=file_id,
                    class_id=class_id,
                    method_id=method_id,
                    metadata=issue_data,
                )

    def _has_pass_statement(self, node: ast.FunctionDef) -> bool:
        """Check if function has only pass statement."""
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            return True
        return False

    def _has_not_implemented_error(self, node: ast.FunctionDef) -> bool:
        """Check if function raises NotImplementedError."""
        for stmt in node.body:
            if isinstance(stmt, ast.Raise):
                if isinstance(stmt.exc, ast.Call):
                    if (
                        isinstance(stmt.exc.func, ast.Name)
                        and stmt.exc.func.id == "NotImplementedError"
                    ):
                        return True
        return False

    def _is_abstract_method(self, node: ast.FunctionDef) -> bool:
        """Check if method is abstract."""
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
                return True
        return False

    def _analyze_import(
        self, node: ast.Import, file_path: Path, file_id: Optional[int] = None
    ) -> None:
        """Analyze import statement."""
        file_path_str = str(file_path)
        for alias in node.names:
            import_key = f"{file_path}:{alias.name}"
            import_info = {
                "name": alias.name,
                "file": file_path_str,
                "line": node.lineno,
                "type": "import",
            }
            self.code_map["imports"][import_key] = import_info

            # Save to database
            if self.database and file_id:
                self.database.add_import(
                    file_id, alias.name, None, "import", node.lineno
                )

        # Check for invalid imports
        if self.issue_detector:
            self.issue_detector.check_invalid_import(node, file_path)

    def _analyze_import_from(
        self, node: ast.ImportFrom, file_path: Path, file_id: Optional[int] = None
    ) -> None:
        """Analyze import from statement."""
        file_path_str = str(file_path)
        module = node.module or ""
        for alias in node.names:
            import_key = f"{file_path}:{alias.name}"
            import_info = {
                "name": alias.name,
                "file": file_path_str,
                "line": node.lineno,
                "type": "import_from",
                "module": module,
            }
            self.code_map["imports"][import_key] = import_info

            # Save to database
            if self.database and file_id:
                self.database.add_import(
                    file_id, alias.name, module, "import_from", node.lineno
                )

        # Check for invalid imports
        if self.issue_detector:
            self.issue_detector.check_invalid_import_from(node, file_path)

    def _get_file_content(self, file_path: Path) -> str:
        """Get file content for AST source segment extraction."""
        if not hasattr(self, "_file_content_cache"):
            self._file_content_cache = {}

        file_path_str = str(file_path)
        if file_path_str not in self._file_content_cache:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self._file_content_cache[file_path_str] = f.read()
            except Exception:
                self._file_content_cache[file_path_str] = ""

        return self._file_content_cache[file_path_str]

    async def _save_ast_tree(
        self,
        tree: ast.Module,
        file_id: int,
        project_id: str,
        file_mtime: float,
        force: bool = False,
    ) -> bool:
        """
        Save AST tree to database with time check.

        Args:
            tree: AST module node
            file_id: File ID in database
            project_id: Project ID
            file_mtime: File modification time
            force: If True, save regardless of time check

        Returns:
            True if AST was saved, False if skipped (not outdated)
        """
        if not self.database:
            return False

        try:
            # Check if AST is outdated (unless force is True)
            if not force:
                if not self.database.is_ast_outdated(file_id, file_mtime):
                    logger.debug(
                        f"AST tree for file_id={file_id} is up to date, skipping"
                    )
                    return False

            # Convert AST to JSON-serializable format
            ast_dict = self._ast_to_dict(tree)

            # Serialize to JSON
            ast_json = json.dumps(ast_dict, indent=2)

            # Calculate hash for change detection
            ast_hash = hashlib.sha256(ast_json.encode("utf-8")).hexdigest()

            # Save to database (overwrite existing)
            await self.database.overwrite_ast_tree(
                file_id=file_id,
                project_id=project_id,
                ast_json=ast_json,
                ast_hash=ast_hash,
                file_mtime=file_mtime,
            )

            logger.debug(f"Saved AST tree for file_id={file_id}, mtime={file_mtime}")
            return True
        except Exception as e:
            logger.error(f"Error saving AST tree for file_id={file_id}: {e}")
            return False

    def _ast_to_dict(self, node: ast.AST) -> Dict[str, Any]:
        """
        Convert AST node to dictionary.

        Args:
            node: AST node

        Returns:
            Dictionary representation of AST node
        """
        if isinstance(node, ast.AST):
            result = {
                "_type": type(node).__name__,
            }
            for field, value in ast.iter_fields(node):
                if isinstance(value, list):
                    result[field] = [self._ast_to_dict(item) for item in value]
                elif isinstance(value, ast.AST):
                    result[field] = self._ast_to_dict(value)
                elif value is Ellipsis or value is ...:
                    # Handle ellipsis (...) which is not JSON serializable
                    result[field] = None
                else:
                    result[field] = value
            return result
        elif isinstance(node, list):
            return [self._ast_to_dict(item) for item in node]
        elif node is Ellipsis or node is ...:
            # Handle ellipsis (...) which is not JSON serializable
            return None
        else:
            return node
