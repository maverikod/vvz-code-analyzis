"""
Resolve grep match lines to preview/edit block identifiers.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from code_analysis.core.structure_extraction.models import StructureDocument

from code_analysis.commands.universal_file_preview.handlers.json_handler import (
    _line_for_json_pointer,
)
from code_analysis.commands.universal_file_preview.handlers.markdown_handler import (
    _iter_md_block_tokens,
    _md_block_node_ref,
)
from code_analysis.commands.universal_file_preview.handlers.yaml_handler import (
    _line_for_yaml_pointer,
)
from code_analysis.core.cst_tree.models import TreeNodeMetadata
from code_analysis.core.cst_tree.tree_sidecar import (
    metadata_map_from_payload,
    read_sidecar_payload,
)
from code_analysis.core.tree_lifecycle.checksum import validate_or_recreate_tree_file
from code_analysis.core.json_tree.tree_builder import build_tree_from_data
from code_analysis.core.yaml_tree.tree_builder import build_yaml_tree_from_data

_PY_SUFFIXES = frozenset({".py", ".pyi", ".pyw"})
_JSON_SUFFIX = ".json"
_YAML_SUFFIXES = frozenset({".yaml", ".yml"})
_MD_SUFFIX = ".md"

_TRIVIAL_NODE_TYPES = frozenset(
    {
        "SimpleWhitespace",
        "TrailingWhitespace",
        "Newline",
        "EmptyLine",
        "Comment",
        "Whitespace",
    }
)

_PREFERRED_SIDECAR_KINDS = frozenset(
    {"method", "function", "class", "stmt", "smallstmt", "module"}
)

_CacheKey = tuple[str, float]


class GrepBlockResolver:
    """Per-file cached lookup from 1-based line number to block id/type.

    Prefer :func:`code_analysis.core.structure_extraction.extract_structure` for
    new code; this class remains for legacy callers.
    """

    def __init__(self) -> None:
        """Initialize per-file structure document and legacy index caches."""
        self._indexes: dict[_CacheKey, _LineBlockIndex | None] = {}
        self._documents: dict[_CacheKey, "StructureDocument | None"] = {}

    def resolve(
        self, abs_path: Path, line_number: int
    ) -> tuple[str | None, str | None]:
        """Resolve a source line to the smallest containing block id and type."""
        from code_analysis.core.structure_extraction.extractor import (
            extract_structure,
            find_smallest_block_containing_line,
        )

        cache_key = _cache_key(abs_path)
        if cache_key not in self._documents:
            try:
                content = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                self._documents[cache_key] = None
            else:
                self._documents[cache_key] = extract_structure(
                    file_path=str(abs_path),
                    content=content,
                    source="disk",
                    ensure_persisted_tree=False,
                )
        document = self._documents.get(cache_key)
        if document is None:
            return None, None
        block = find_smallest_block_containing_line(document, line_number)
        if block is None:
            return None, None
        return block.block_id, block.node_type

    def cleanup(self) -> None:
        """Clear cached structure documents and line indexes."""
        self._indexes.clear()
        self._documents.clear()


class _LineBlockIndex:
    """Interface for mapping a 1-based line number to block metadata."""

    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        """Return the block id and type for a line, if any."""
        raise NotImplementedError


class _SidecarPythonLineBlockIndex(_LineBlockIndex):
    """Lookup via TreeLifecycle-validated sibling ``<source>.py.tree`` metadata_map (no in-memory CST session)."""

    def __init__(self, metadata_map: dict[str, TreeNodeMetadata]) -> None:
        """Store sidecar node metadata and initialize the line lookup cache."""
        self._metadata = list(metadata_map.values())
        self._cache: dict[int, tuple[str | None, str | None]] = {}

    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        """Return the narrowest preferred sidecar node containing the line."""
        if line_number in self._cache:
            return self._cache[line_number]
        candidates = [
            meta
            for meta in self._metadata
            if meta.start_line <= line_number <= meta.end_line
            and meta.type not in _TRIVIAL_NODE_TYPES
            and meta.kind in _PREFERRED_SIDECAR_KINDS
        ]
        if not candidates:
            result = (None, None)
        else:
            best = min(
                candidates,
                key=lambda meta: (
                    meta.end_line - meta.start_line,
                    meta.start_line,
                ),
            )
            result = (best.stable_id, best.type)
        self._cache[line_number] = result
        return result


class _StructuredLineBlockIndex(_LineBlockIndex):
    """Line lookup backed by a precomputed structured document map."""

    def __init__(self, line_map: dict[int, tuple[str, str]]) -> None:
        """Store a direct line-to-block mapping."""
        self._line_map = line_map

    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        """Return the structured block mapped to the line."""
        hit = self._line_map.get(line_number)
        if hit is None:
            return None, None
        return hit[0], hit[1]


class _MarkdownLineBlockIndex(_LineBlockIndex):
    """Line lookup backed by markdown-it block token spans."""

    def __init__(self, abs_path: Path, tokens: list[Any]) -> None:
        """Store markdown block tokens and initialize a line lookup cache."""
        self._file_path = str(abs_path.resolve())
        self._tokens = tokens
        self._cache: dict[int, tuple[str | None, str | None]] = {}

    def lookup(self, line_number: int) -> tuple[str | None, str | None]:
        """Return the narrowest markdown token covering the line."""
        if line_number in self._cache:
            return self._cache[line_number]
        zero_line = line_number - 1
        best = None
        best_span: int | None = None
        for token in self._tokens:
            if token.map is None:
                continue
            start, end = token.map
            if start <= zero_line < end:
                span = end - start
                if best is None or span <= best_span:
                    best = token
                    best_span = span
        if best is None:
            result = (None, None)
        else:
            result = (_md_block_node_ref(self._file_path, best), best.type)
        self._cache[line_number] = result
        return result


def _cache_key(abs_path: Path) -> _CacheKey:
    """Return a cache key that invalidates when file mtime changes."""
    resolved = abs_path.resolve()
    try:
        mtime = resolved.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (str(resolved), mtime)


def _build_line_to_node_id_map(
    source: str,
    metadata_map: dict[str, Any],
    line_for_pointer,
    pointer_attr: str,
) -> dict[int, tuple[str, str]]:
    """
    Expand annotated start-line refs to every source line (nearest ancestor node).

    Same strategy as universal_file_preview annotated_full_text: map each node's
    start line via pointer heuristics, then assign each file line the deepest
    node whose start line is still on or above that line.
    """
    lines = source.splitlines()
    if not lines:
        return {}
    starts: list[tuple[int, str, str]] = []
    for meta in metadata_map.values():
        pointer = getattr(meta, pointer_attr, "")
        start = getattr(meta, "start_line", None)
        if start is None:
            start = line_for_pointer(lines, pointer)
        if start is None:
            continue
        starts.append((start, meta.node_id, meta.kind))
    starts.sort(key=lambda item: item[0])
    if not starts:
        return {}
    line_map: dict[int, tuple[str, str]] = {}
    for line_num in range(1, len(lines) + 1):
        best: tuple[str, str] | None = None
        best_start = -1
        for start, node_id, kind in starts:
            if start <= line_num and start >= best_start:
                best_start = start
                best = (node_id, kind)
        if best is not None:
            line_map[line_num] = best
    return line_map


def _load_python_sidecar_index(abs_path: Path) -> _SidecarPythonLineBlockIndex | None:
    """Load a Python sidecar tree as a line block index when available."""
    resolved = abs_path.resolve()
    try:
        tree_ref, _state = validate_or_recreate_tree_file(
            project_root=resolved.parent,
            file_path=resolved.name,
        )
    except (FileNotFoundError, ValueError, OSError, NotImplementedError):
        return None
    if not tree_ref.sidecar_path.is_file():
        return None
    payload = read_sidecar_payload(abs_path)
    if payload is None:
        return None
    meta_blob = payload.get("metadata_map")
    order_raw = payload.get("metadata_node_order")
    order = [str(x) for x in order_raw] if isinstance(order_raw, list) else None
    metadata_map = metadata_map_from_payload(meta_blob, order)
    if not metadata_map:
        return None
    return _SidecarPythonLineBlockIndex(metadata_map)


def _build_index(abs_path: Path) -> _LineBlockIndex | None:
    """Build the best available line block index for a supported file type."""
    suffix = abs_path.suffix.lower()
    try:
        if suffix in _PY_SUFFIXES:
            return _load_python_sidecar_index(abs_path)
        source = abs_path.read_text(encoding="utf-8", errors="replace")
        if suffix == _JSON_SUFFIX:
            import json

            data = json.loads(source)
            tree = build_tree_from_data(str(abs_path.resolve()), data)
            line_map = _build_line_to_node_id_map(
                source,
                tree.metadata_map,
                _line_for_json_pointer,
                "json_pointer",
            )
            return _StructuredLineBlockIndex(line_map)
        if suffix in _YAML_SUFFIXES:
            import yaml

            data = yaml.safe_load(source)
            tree = build_yaml_tree_from_data(str(abs_path.resolve()), data)
            line_map = _build_line_to_node_id_map(
                source,
                tree.metadata_map,
                _line_for_yaml_pointer,
                "yaml_pointer",
            )
            return _StructuredLineBlockIndex(line_map)
        if suffix == _MD_SUFFIX:
            from markdown_it import MarkdownIt

            tokens = list(_iter_md_block_tokens(MarkdownIt().parse(source)))
            return _MarkdownLineBlockIndex(abs_path, tokens)
    except Exception:
        return None
    return None
