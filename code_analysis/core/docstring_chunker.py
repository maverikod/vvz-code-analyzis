"""
Module for extracting and chunking docstrings and comments with AST node binding.

Extracts all docstrings and comments from code with precise AST node binding,
sends them to chunker service, gets embeddings, and saves to database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import json
import logging
import uuid
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .svo_client_manager import SVOClientManager
    from .faiss_manager import FaissIndexManager

logger = logging.getLogger(__name__)


class DocstringChunker:
    """
    Extracts docstrings and comments with AST node binding, chunks them, and saves to database.
    """

    def __init__(
        self,
        database,
        svo_client_manager: Optional["SVOClientManager"] = None,
        faiss_manager: Optional["FaissIndexManager"] = None,
        min_chunk_length: int = 30,
    ):
        """
        Initialize docstring chunker.

        Args:
            database: CodeDatabase instance
            svo_client_manager: SVO client manager for chunking and embedding
            faiss_manager: FAISS index manager for vector storage
            min_chunk_length: Minimum text length for chunking (default: 30)
        """
        self.database = database
        self.svo_client_manager = svo_client_manager
        self.faiss_manager = faiss_manager
        self.min_chunk_length = min_chunk_length
        # Binding levels: 0 ok, 1 file, 2 class, 3 method/function, 4 node, 5 line
        self.binding_levels = {
            "file": 1,
            "class": 2,
            "method": 3,
            "function": 3,
            "node": 4,
            "line": 5,
        }

    def _find_node_context(
        self, node: ast.AST, tree: ast.Module
    ) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
        """
        Find context for AST node (class_id, function_id, method_id).

        Args:
            node: AST node
            tree: AST module

        Returns:
            Tuple of (class_id, function_id, method_id, line)
        """
        class_id = None
        function_id = None
        method_id = None
        line = getattr(node, "lineno", None)

        # Walk tree to find parent context
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                # Check if node is within this class
                if hasattr(node, "lineno") and hasattr(parent, "lineno"):
                    if parent.lineno <= node.lineno:
                        # Check if node is in class body
                        if hasattr(parent, "end_lineno") and parent.end_lineno:
                            if node.lineno <= parent.end_lineno:
                                # Get class_id from database
                                # We'll need to pass this information differently
                                class_id = parent.name  # Store name, resolve ID later
                        else:
                            # Fallback: check if node is in class body by walking
                            for item in parent.body:
                                if item == node or (
                                    hasattr(item, "lineno")
                                    and hasattr(node, "lineno")
                                    and item.lineno == node.lineno
                                ):
                                    class_id = parent.name
                                    # Check if it's a method
                                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                        method_id = node.name
                                    break

            elif isinstance(parent, ast.FunctionDef) and not class_id:
                # Top-level function
                if hasattr(node, "lineno") and hasattr(parent, "lineno"):
                    if parent.lineno == node.lineno and parent == node:
                        function_id = parent.name

        return (class_id, function_id, method_id, line)

    def extract_docstrings_and_comments(
        self, tree: ast.Module, file_content: str
    ) -> List[Dict[str, Any]]:
        """
        Extract all docstrings and comments from AST with context binding.

        Args:
            tree: AST module node
            file_content: Original file content

        Returns:
            List of extracted text items with metadata including AST node binding
        """
        items = []
        lines = file_content.split("\n")

        # Extract file-level docstring
        file_docstring = ast.get_docstring(tree)
        if file_docstring:
            items.append({
                "type": "file_docstring",
                "text": file_docstring,
                "line": 1,
                "ast_node_type": "Module",
                "entity_type": "file",
                "entity_name": None,
                "class_name": None,
                "function_name": None,
                "method_name": None,
            })

        # Extract docstrings and comments from all nodes with context
        # Use recursive visitor to maintain parent context
        def visit_node(node: ast.AST, parent_class: Optional[str] = None, parent_function: Optional[str] = None):
            """Recursively visit AST nodes with parent context."""
            node_type = type(node).__name__

            # Extract docstrings (only from nodes that can have docstrings)
            # ast.get_docstring() works only for Module, ClassDef, FunctionDef, AsyncFunctionDef
            # In Python 3.12+, it raises ValueError for nodes that can't have docstrings
            docstring = None
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                try:
                    docstring = ast.get_docstring(node)
                except (ValueError, TypeError, AttributeError):
                    # Some nodes can't have docstrings (e.g., Expr)
                    # In Python 3.12+, ValueError is raised: "'Expr' can't have docstrings"
                    # This is expected for nodes that don't support docstrings
                    docstring = None
            
            if docstring:
                class_name = None
                function_name = None
                method_name = None
                entity_type = None
                entity_name = None

                if isinstance(node, ast.ClassDef):
                    entity_type = "class"
                    entity_name = node.name
                    class_name = node.name
                    # Recursively visit class body with class context
                    for child in node.body:
                        visit_node(child, parent_class=node.name, parent_function=None)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    entity_name = node.name
                    if parent_class:
                        # It's a method
                        entity_type = "method"
                        method_name = node.name
                        class_name = parent_class
                    else:
                        # It's a function
                        entity_type = "function"
                        function_name = node.name
                    # Recursively visit function body
                    for child in node.body:
                        visit_node(child, parent_class=parent_class, parent_function=node.name)
                else:
                    # Module docstring (already handled above)
                    return

                items.append({
                    "type": "docstring",
                    "text": docstring,
                    "line": getattr(node, "lineno", None),
                    "ast_node_type": node_type,
                    "entity_type": entity_type,
                    "entity_name": entity_name,
                    "class_name": class_name,
                    "function_name": function_name,
                    "method_name": method_name,
                    "node": node,  # Keep reference for later ID resolution
                })
            else:
                # Not a docstring node, but may have children
                if isinstance(node, ast.ClassDef):
                    for child in node.body:
                        visit_node(child, parent_class=node.name, parent_function=None)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for child in node.body:
                        visit_node(child, parent_class=parent_class, parent_function=node.name)
                elif hasattr(node, "body") and isinstance(node.body, list):
                    # Other nodes with body (e.g., If, For, While, etc.)
                    for child in node.body:
                        visit_node(child, parent_class=parent_class, parent_function=parent_function)
        
        # Start visiting from module body
        for node in tree.body:
            visit_node(node)

        # Extract comments with proper context binding
        def visit_node_for_comments(node: ast.AST, parent_class: Optional[str] = None, parent_function: Optional[str] = None):
            """Recursively visit AST nodes to extract comments with parent context."""
            if hasattr(node, "lineno"):
                node_line = node.lineno - 1
                if 0 <= node_line < len(lines):
                    line = lines[node_line]
                    # Check for inline comment
                    if "#" in line:
                        comment_start = line.find("#")
                        comment_text = line[comment_start + 1:].strip()
                        if comment_text:
                            # Use parent context from recursive traversal
                            class_name = parent_class
                            function_name = parent_function
                            method_name = None
                            entity_type = None

                            # Determine entity type based on context
                            if parent_class:
                                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                    entity_type = "method_comment"
                                    method_name = node.name
                                else:
                                    entity_type = "class_comment"
                            elif parent_function:
                                entity_type = "function_comment"
                            else:
                                entity_type = "comment"

                            items.append({
                                "type": "comment",
                                "text": comment_text,
                                "line": node.lineno,
                                "ast_node_type": type(node).__name__,
                                "entity_type": entity_type,
                                "entity_name": None,
                                "class_name": class_name,
                                "function_name": function_name,
                                "method_name": method_name,
                                "node": node,
                            })

            # Recursively visit children with updated context
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    visit_node_for_comments(child, parent_class=node.name, parent_function=None)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in node.body:
                    visit_node_for_comments(child, parent_class=parent_class, parent_function=node.name)
            elif hasattr(node, "body") and isinstance(node.body, list):
                for child in node.body:
                    visit_node_for_comments(child, parent_class=parent_class, parent_function=parent_function)
        
        # Start visiting from module body for comments
        for node in tree.body:
            visit_node_for_comments(node)

        return items

    async def process_file(
        self,
        file_path: Path,
        file_id: int,
        project_id: str,
        tree: ast.Module,
        file_content: str,
    ) -> None:
        """
        Process file: extract, chunk, embed, and save to database with AST node binding.

        Args:
            file_path: Path to file
            file_id: File ID in database
            project_id: Project ID
            tree: AST tree
            file_content: File content
        """
        if not self.svo_client_manager:
            logger.debug("SVO client manager not available, skipping chunking")
            return

        # Extract docstrings and comments with context
        items = self.extract_docstrings_and_comments(tree, file_content)
        if not items:
            logger.debug(f"No docstrings or comments found in {file_path}")
            return

        # Get min_chunk_length from config if available
        min_length = self.min_chunk_length
        if self.svo_client_manager and hasattr(self.svo_client_manager, 'config'):
            server_config = self.svo_client_manager.config
            if server_config and hasattr(server_config, 'min_chunk_length'):
                min_length = server_config.min_chunk_length

        # Separate items into long (>= min_length) and short (< min_length)
        long_items = []
        short_items = []
        
        for item in items:
            text = item.get("text", "").strip()
            if not text:
                continue
            if len(text) >= min_length:
                long_items.append(item)
            else:
                short_items.append(item)
        
        logger.info(
            f"File {file_path}: {len(long_items)} long items (>= {min_length} chars), "
            f"{len(short_items)} short items (< {min_length} chars)"
        )

        # Process long items separately (each one individually)
        for item in long_items:
            await self._process_single_item(
                item, file_path, file_id, project_id
            )

        # Group short items by level and process
        if short_items:
            await self._process_short_items_grouped(
                short_items, file_path, file_id, project_id, min_length
            )

    async def _process_single_item(
        self,
        item: Dict[str, Any],
        file_path: Path,
        file_id: int,
        project_id: str,
    ) -> None:
        """
        Process a single item (long text >= min_length).

        Args:
            item: Item dictionary with text and metadata
            file_path: Path to file
            file_id: File ID in database
            project_id: Project ID
        """
        text = item.get("text", "").strip()
        if not text:
            return

        try:
            logger.info(
                f"Chunking {item['type']} at line {item.get('line')} in {file_path}: "
                f"text length={len(text)}, preview: {text[:100]}..."
            )
            
            if not self.svo_client_manager:
                logger.error("SVO client manager is not available, skipping chunking")
                return
            
            logger.info(
                f"🔍 Requesting chunking for {item['type']} at line {item.get('line')} "
                f"in {file_path}, text length={len(text)}"
            )
            logger.info(
                f"📝 Text to chunk (length={len(text)}): {repr(text[:500])}"
                f"{'...' if len(text) > 500 else ''}"
            )
            chunks = await self.svo_client_manager.chunk_text(
                text,
                type="DocBlock",
            )

            if not chunks:
                logger.warning(
                    f"⚠️  No chunks returned for {item['type']} at line {item.get('line')} "
                    f"in {file_path}, text length={len(text)}"
                )
                return
            
            logger.info(
                f"✅ Received {len(chunks)} chunks for {item['type']} at line {item.get('line')} "
                f"in {file_path}, text length={len(text)}"
            )

            # Resolve entity IDs and save chunks
            await self._save_chunks(
                chunks, item, file_path, file_id, project_id
            )

        except Exception as e:
            logger.warning(
                f"Failed to chunk {item['type']} at line {item.get('line')} "
                f"in {file_path}: {e}. Skipping this item."
            )

    async def _process_short_items_grouped(
        self,
        short_items: List[Dict[str, Any]],
        file_path: Path,
        file_id: int,
        project_id: str,
        min_length: int,
    ) -> None:
        """
        Group short items by level (method -> class -> file) and process.

        Logic:
        1. Group by method (class_name + method_name)
        2. If method group total < min_length, merge with class group
        3. If class group total < min_length, merge with file group
        4. If file group total < min_length, skip chunking

        Args:
            short_items: List of short items (< min_length)
            file_path: Path to file
            file_id: File ID in database
            project_id: Project ID
            min_length: Minimum length for chunking
        """
        # Group by method level: (class_name, method_name)
        method_groups: Dict[Tuple[Optional[str], Optional[str]], List[Dict[str, Any]]] = {}
        
        # Group by class level: (class_name, None)
        class_groups: Dict[Optional[str], List[Dict[str, Any]]] = {}
        
        # File level: all items
        file_group: List[Dict[str, Any]] = []

        for item in short_items:
            class_name = item.get("class_name")
            method_name = item.get("method_name")
            function_name = item.get("function_name")
            
            # Determine grouping key
            if class_name and method_name:
                # Method level
                key = (class_name, method_name)
                if key not in method_groups:
                    method_groups[key] = []
                method_groups[key].append(item)
            elif class_name:
                # Class level (property, class docstring, etc.)
                if class_name not in class_groups:
                    class_groups[class_name] = []
                class_groups[class_name].append(item)
            else:
                # File level (file docstring, top-level function, etc.)
                file_group.append(item)

        # Process method groups
        for (class_name, method_name), method_items in method_groups.items():
            total_length = sum(len(item.get("text", "")) for item in method_items)
            
            if total_length >= min_length:
                # Chunk method group
                await self._chunk_grouped_items(
                    method_items, f"method {class_name}.{method_name}",
                    file_path, file_id, project_id, binding_level=self.binding_levels.get("method", 3)
                )
            else:
                # Merge with class group
                if class_name not in class_groups:
                    class_groups[class_name] = []
                class_groups[class_name].extend(method_items)
                logger.debug(
                    f"Method {class_name}.{method_name} group ({total_length} chars) "
                    f"merged with class {class_name} group"
                )

        # Process class groups
        for class_name, class_items in class_groups.items():
            total_length = sum(len(item.get("text", "")) for item in class_items)
            
            if total_length >= min_length:
                # Chunk class group
                await self._chunk_grouped_items(
                    class_items, f"class {class_name}",
                    file_path, file_id, project_id, binding_level=self.binding_levels.get("class", 2)
                )
            else:
                # Merge with file group
                file_group.extend(class_items)
                logger.debug(
                    f"Class {class_name} group ({total_length} chars) "
                    f"merged with file group"
                )

        # Process file group
        if file_group:
            total_length = sum(len(item.get("text", "")) for item in file_group)
            
            if total_length >= min_length:
                # Chunk file group
                await self._chunk_grouped_items(
                    file_group, "file",
                    file_path, file_id, project_id, binding_level=self.binding_levels.get("file", 1)
                )
            else:
                # Skip - total length still too short
                logger.debug(
                    f"File group total length ({total_length} chars) < {min_length}, "
                    f"skipping chunking for {len(file_group)} items"
                )

    async def _chunk_grouped_items(
        self,
        items: List[Dict[str, Any]],
        group_name: str,
        file_path: Path,
        file_id: int,
        project_id: str,
        binding_level: int = 0,
    ) -> None:
        """
        Chunk a group of items together.

        Args:
            items: List of items to chunk together
            group_name: Name of the group (for logging)
            file_path: Path to file
            file_id: File ID in database
            project_id: Project ID
        """
        # Combine texts with separator
        texts = [item.get("text", "").strip() for item in items if item.get("text", "").strip()]
        if not texts:
            return
        
        combined_text = "\n\n".join(texts)
        total_length = len(combined_text)
        
        logger.info(
            f"Chunking grouped {group_name} items ({len(items)} items, "
            f"total {total_length} chars) in {file_path}"
        )
        logger.debug(
            "Docstring chunk request preview",
            extra={
                "file": str(file_path),
                "group": group_name,
                "items": len(items),
                "total_length": total_length,
                "preview": combined_text[:200],
            },
        )
        
        chunks = None
        try:
            chunks = await self.svo_client_manager.chunk_text(
                combined_text,
                type="DocBlock",
            )
        except Exception as e:
            logger.warning(
                f"Failed to chunk grouped {group_name} items in {file_path}: {e}"
            )

        if not chunks:
            # Fallback: try chunking at higher level (file-level) to avoid empty result
            logger.warning(
                f"No chunks returned for grouped {group_name} items in {file_path}, "
                "attempting fallback at file level"
            )
            try:
                chunks = await self.svo_client_manager.chunk_text(
                    combined_text,
                    type="DocBlock",
                )
            except Exception as e:
                logger.warning(
                    f"Fallback chunking failed for grouped {group_name} in {file_path}: {e}"
                )
                return

        if not chunks:
            logger.warning(
                f"No chunks returned for grouped {group_name} items in {file_path} after fallback"
            )
            return

        logger.info(
            f"Received {len(chunks)} chunks for grouped {group_name} items in {file_path}"
        )

        # Save chunks - need to distribute to original items
        # For grouped chunks, we'll use the first item's context for all chunks
        # This is a limitation - chunks from grouped items lose individual context
        if items:
            primary_item = items[0]  # Use first item's context
            await self._save_chunks(
                chunks,
                primary_item,
                file_path,
                file_id,
                project_id,
                binding_level=binding_level or self.binding_levels.get("file", 1),
            )

    async def _save_chunks(
        self,
        chunks: List[Any],
        item: Dict[str, Any],
        file_path: Path,
        file_id: int,
        project_id: str,
        binding_level: int = 0,
    ) -> None:
        """
        Save chunks to database with embeddings and BM25.

        Args:
            chunks: List of chunks from chunker
            item: Original item with metadata
            file_path: Path to file
            file_id: File ID in database
            project_id: Project ID
        """
        # Resolve entity IDs from database
        class_id = None
        function_id = None
        method_id = None

        if item.get("class_name"):
            with self.database._lock:
                assert self.database.conn is not None
                cursor = self.database.conn.cursor()
                cursor.execute(
                    "SELECT id FROM classes WHERE file_id = ? AND name = ?",
                    (file_id, item["class_name"]),
                )
                row = cursor.fetchone()
                if row:
                    class_id = row[0]

                    # If it's a method, get method_id
                    if item.get("method_name"):
                        cursor.execute(
                            "SELECT id FROM methods WHERE class_id = ? AND name = ?",
                            (class_id, item["method_name"]),
                        )
                        row = cursor.fetchone()
                        if row:
                            method_id = row[0]

        if item.get("function_name") and not method_id:
            with self.database._lock:
                assert self.database.conn is not None
                cursor = self.database.conn.cursor()
                cursor.execute(
                    "SELECT id FROM functions WHERE file_id = ? AND name = ?",
                    (file_id, item["function_name"]),
                )
                row = cursor.fetchone()
                if row:
                    function_id = row[0]

        # Save chunks to database with embeddings and BM25
        for idx, chunk in enumerate(chunks):
            chunk_uuid = str(uuid.uuid4())
            chunk_text = getattr(chunk, "body", "") or getattr(chunk, "text", "")
            chunk_type = getattr(chunk, "type", "DocBlock") or "DocBlock"
            chunk_ordinal = getattr(chunk, "ordinal", None)
            
            # Extract embedding if chunker returned it (chunker may return embeddings)
            embedding = None
            embedding_vector_json = None
            embedding_model = None
            vector_id = None
            
            # Check if chunk has embedding from chunker
            if hasattr(chunk, "embedding") and getattr(chunk, "embedding", None) is not None:
                embedding = getattr(chunk, "embedding")
                # Convert to JSON string for database storage
                import json
                try:
                    if hasattr(embedding, "tolist"):
                        embedding_vector_json = json.dumps(embedding.tolist())
                    elif isinstance(embedding, (list, tuple)):
                        embedding_vector_json = json.dumps(list(embedding))
                    else:
                        embedding_vector_json = json.dumps(embedding)
                    embedding_model = getattr(chunk, "embedding_model", None)
                    logger.debug(
                        f"Chunk {idx+1}/{len(chunks)} has embedding from chunker "
                        f"(model={embedding_model})"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to serialize embedding for chunk {idx+1}: {e}"
                    )
            else:
                # Embedding will be obtained by vectorization worker
                logger.debug(
                    f"Chunk {idx+1}/{len(chunks)} has no embedding from chunker, "
                    "will be processed by vectorization worker"
                )
            
            # Extract BM25 score
            bm25_score = None
            if hasattr(chunk, "bm25"):
                bm25_score = getattr(chunk, "bm25", None)
            elif hasattr(chunk, "bm25_score"):
                bm25_score = getattr(chunk, "bm25_score", None)
            
            # Save chunk to database
            chunk_id = await self.database.add_code_chunk(
                file_id=file_id,
                project_id=project_id,
                chunk_uuid=chunk_uuid,
                chunk_type=chunk_type,
                chunk_text=chunk_text,
                chunk_ordinal=chunk_ordinal,
                vector_id=vector_id,
                embedding_model=embedding_model,
                bm25_score=bm25_score,
                embedding_vector=embedding_vector_json,
                class_id=class_id,
                function_id=function_id,
                method_id=method_id,
                line=item.get("line"),
                ast_node_type=item.get("ast_node_type"),
                source_type=item.get("type"),
                binding_level=binding_level,
            )
            
            logger.info(
                f"Saved chunk {idx+1}/{len(chunks)} to database: id={chunk_id}, "
                f"vector_id={vector_id}, has_embedding={embedding_vector_json is not None}, "
                f"has_bm25={bm25_score is not None}"
            )

    async def close(self) -> None:
        """Close client connections."""
        # SVOClientManager handles its own cleanup
        pass
