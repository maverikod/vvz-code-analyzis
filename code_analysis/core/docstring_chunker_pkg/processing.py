"""
Module processing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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
    if self.svo_client_manager and hasattr(self.svo_client_manager, "config"):
        server_config = self.svo_client_manager.config
        if server_config and hasattr(server_config, "min_chunk_length"):
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
        await self._process_single_item(item, file_path, file_id, project_id)

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
        await self._save_chunks(chunks, item, file_path, file_id, project_id)

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
        item.get("function_name")

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
                method_items,
                f"method {class_name}.{method_name}",
                file_path,
                file_id,
                project_id,
                binding_level=self.binding_levels.get("method", 3),
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
                class_items,
                f"class {class_name}",
                file_path,
                file_id,
                project_id,
                binding_level=self.binding_levels.get("class", 2),
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
                file_group,
                "file",
                file_path,
                file_id,
                project_id,
                binding_level=self.binding_levels.get("file", 1),
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
    texts = [
        item.get("text", "").strip() for item in items if item.get("text", "").strip()
    ]
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
