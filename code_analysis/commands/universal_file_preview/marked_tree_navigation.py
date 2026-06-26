"""
PreviewNavigation adapter for universal_file_preview (G-004 {f001}, {f002}).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_analysis.tree.contracts import NodeId
from code_analysis.tree.preview_navigation import (
    PreviewNavigation,
    PreviewNavigationError,
    PreviewTextMode,
    _build_indexes,
    _iter_all_nodes,
    apply_line_id_prefixes,
    compute_line_span,
    compute_max_short_id_in_tree,
)
from code_analysis.tree.preview_selector import (
    DEFAULT_FULL_TEXT_MAX_LINES,
    PreviewSelector,
    PreviewSelectorConfig,
    PreviewSelectorError,
    format_key_from_extension,
)

from .base_handler import FileHandler
from .budget import PreviewBudget
from .errors import (
    INPUT_ERROR_INVALID_SELECTOR_FORM,
    INPUT_ERROR_UNKNOWN_NODE_REF,
    PreviewError,
    input_error,
)
from .marked_tree_loader import (
    NodeListTree,
    _read_source_text,
    make_preview_tree_loader,
    parse_focus_short_id,
    resolve_format_handler,
)
from .models import Block, NavigationResult, Node, NodeKind
from .node_ref_params import normalize_optional_node_ref
from .invalid_preview import invalid_source_node
from .preview_addressing import preview_source_is_parseable
from code_analysis.core.tree_lifecycle.lifecycle import TreeLifecycle
from code_analysis.core.tree_lifecycle.node_id_map import TreeSections, parse_tree_file

_PYTHON_EXTENSIONS = frozenset({".py", ".pyi", ".pyw"})
_SCALAR_KINDS = frozenset({"scalar", "string", "number", "boolean", "null"})


def looks_like_json_pointer_node_ref(node_ref: object) -> bool:
    """True when ``node_ref`` is RFC 6901-style (tree-temp / legacy preview)."""
    if not isinstance(node_ref, str):
        return False
    return bool(node_ref.strip().startswith("/"))


def _preview_source_is_parseable(params: dict[str, Any]) -> bool:
    """Return False when structural parse fails — caller must use plain-text fallback."""
    return preview_source_is_parseable(Path(str(params.get("file_path", ""))))


def _preview_handler_id(source_abs: Path) -> str | None:
    """Return preview handler id."""
    ext = source_abs.suffix.lower()
    if ext == ".json":
        return "json"
    if ext in (".yml", ".yaml"):
        return "yaml"
    if ext == ".md":
        return "markdown"
    return None


def _load_tree_sections_for_preview(params: dict[str, Any]) -> TreeSections | None:
    """Load MAP/TREE sections from sibling ``.tree`` sidecar (create via lifecycle if needed)."""
    preview_abs_path = Path(str(params["file_path"]))
    project_root = params.get("project_root")
    rel_file_path = params.get("rel_file_path")
    if project_root is not None and rel_file_path:
        try:
            TreeLifecycle.from_path(
                project_root=Path(str(project_root)),
                file_path=str(rel_file_path),
            )
        except Exception:
            pass
    try:
        handler = resolve_format_handler(preview_abs_path)
        sidecar = handler.sidecar_path(preview_abs_path.resolve())
        if not sidecar.is_file():
            return None
        return parse_tree_file(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return None


def normalize_marked_tree_node_ref(params: dict[str, Any]) -> PreviewError | None:
    """Map API ``node_ref`` to integer short_id string for marked-tree navigation.

    Accepts int, decimal string, MAP UUID4, JSON Pointer, or markdown slug; all
    resolve to ``short_id`` via the loaded tree file MAP section.
    """
    raw = params.get("node_ref")
    if raw is None:
        return None
    if isinstance(raw, int):
        params["node_ref"] = str(raw)
        return None
    text = str(raw).strip()
    if not text:
        params["node_ref"] = None
        return None
    if text.isdigit():
        params["node_ref"] = text
        return None

    sections = _load_tree_sections_for_preview(params)
    if sections is None:
        return input_error(
            INPUT_ERROR_UNKNOWN_NODE_REF,
            f"node_ref {raw!r} requires a tree sidecar; run preview at file root first",
            details={"node_ref": raw},
        )
    preview_abs = Path(str(params["file_path"])).resolve()
    unmarked = _read_source_text(preview_abs_path=preview_abs)
    from code_analysis.core.edit_session.edit_operations_adapter import (
        resolve_node_ref_to_short_id,
    )

    try:
        short_id = resolve_node_ref_to_short_id(
            text,
            sections,
            source_abs=preview_abs,
            unmarked_source=unmarked,
            handler_id=_preview_handler_id(preview_abs),
        )
    except ValueError as exc:
        return input_error(
            INPUT_ERROR_UNKNOWN_NODE_REF,
            str(exc),
            details={"node_ref": raw},
        )
    params["node_ref"] = str(short_id)
    return None


def resolve_session_pointer_node_ref(params: dict[str, Any]) -> None:
    """Map JSON Pointer ``node_ref`` to integer short_id for valid edit sessions."""
    node_ref = params.get("node_ref")
    if not looks_like_json_pointer_node_ref(node_ref):
        return
    session_id = params.get("session_id")
    if session_id is None:
        return
    from code_analysis.commands.universal_file_edit.session import get_session
    from code_analysis.core.edit_session.edit_operations_adapter import (
        resolve_node_ref_to_short_id,
    )
    from code_analysis.core.tree_lifecycle.node_id_map import parse_tree_file

    try:
        edit_sess = get_session(str(session_id))
        core = edit_sess.core
        if not core.session_tree_path.is_file():
            return
        sections = parse_tree_file(core.session_tree_path.read_text(encoding="utf-8"))
        short_id = resolve_node_ref_to_short_id(
            str(node_ref),
            sections,
            source_abs=core.source_abs,
            unmarked_source=core.session_source_path.read_text(encoding="utf-8"),
            handler_id=edit_sess.handler_id,
        )
        params["node_ref"] = str(short_id)
    except Exception:
        return


def should_use_marked_tree_navigation(
    handler: FileHandler,
    params: dict[str, Any],
) -> bool:
    """Return True when PreviewNavigation + TreeLifecycle should handle the request."""
    del handler  # format selection uses HandlerRegistry, not preview FileHandler
    file_path = Path(str(params.get("file_path", "")))
    if not params.get("project_root") or not params.get("rel_file_path"):
        return False
    ext = file_path.suffix.lower()
    if ext in _PYTHON_EXTENSIONS:
        try:
            resolve_format_handler(file_path)
        except Exception:
            return False
        return True
    if not _preview_source_is_parseable(params):
        return False
    if isinstance(params.get("selector"), list) and params["selector"]:
        first = params["selector"][0]
        if isinstance(first, str) and not str(first).strip().isdigit():
            return False
    try:
        resolve_format_handler(file_path)
    except Exception:
        return False
    return True


def _kind_to_node_kind(kind: str) -> NodeKind:
    """Return kind to node kind."""
    normalized = (kind or "").lower()
    if normalized in _SCALAR_KINDS:
        return NodeKind.SCALAR
    if normalized in ("object", "mapping"):
        return NodeKind.MAPPING
    if normalized == "array":
        return NodeKind.SEQUENCE
    if normalized == "sequence":
        return NodeKind.SEQUENCE
    if normalized == "lines":
        return NodeKind.LINES
    return NodeKind.TREE_NODE


def _scalar_display_value(node: Any) -> str | None:
    """Extract a legacy-style ``attributes.value`` string for scalar focus nodes."""
    kind = str(getattr(node, "kind", "") or "")
    if kind not in _SCALAR_KINDS:
        return None
    raw_content = getattr(node, "content", None)
    if not isinstance(raw_content, str) or not raw_content.strip():
        return None
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        text = raw_content.strip()
        if text.endswith("..."):
            text = text[:-3].strip()
        return text
    if parsed is None:
        return "null"
    if isinstance(parsed, bool):
        return "true" if parsed else "false"
    if isinstance(parsed, str):
        return parsed
    return str(parsed)


def _tree_node_to_preview_node(node: Any) -> Node:
    """Return tree node to preview node."""
    attrs = dict(getattr(node, "attributes", None) or {})
    kind = str(getattr(node, "kind", "") or "")
    short_id = int(getattr(node, "short_id"))
    name = attrs.get("name")
    if name is not None and not isinstance(name, str):
        name = str(name)
    scalar_value = _scalar_display_value(node)
    if scalar_value is not None and "value" not in attrs:
        attrs["value"] = scalar_value
    return Node(
        node_kind=_kind_to_node_kind(kind),
        node_ref=str(short_id),
        type_label=kind,
        name=name if isinstance(name, str) else None,
        attributes=attrs,
    )


def _preview_block_record_to_block(record: Any) -> Block:
    """Return preview block record to block."""
    sid = int(record.short_id)
    kind = str(record.type_label or "")
    summary: dict[str, Any] = {
        "type": kind,
        "short_id": sid,
        "attribute_summary": record.attribute_summary,
        "render_mode": record.render_mode.value,
        "line_span": record.line_span,
    }
    return Block(
        node_kind=_kind_to_node_kind(kind),
        node_ref=str(sid),
        summary=summary,
        text=record.text_excerpt or None,
    )


def _document_level_blocks(tree: Any) -> list[Any]:
    """Top-level nodes for root_view when the marked tree has no single container root."""
    nodes = list(_iter_all_nodes(tree))
    return sorted(
        [n for n in nodes if getattr(n, "parent_short_id", None) is None],
        key=lambda n: int(getattr(n, "short_id", 0)),
    )


def _document_line_to_short_id(tree: Any) -> dict[int, NodeId]:
    """Return document line to short id."""
    mapping: dict[int, NodeId] = {}
    for node in _iter_all_nodes(tree):
        attrs = getattr(node, "attributes", None) or {}
        start = attrs.get("start_line")
        end = attrs.get("end_line")
        line_no = attrs.get("line_no")
        sid = getattr(node, "short_id", None)
        if not isinstance(sid, int):
            continue
        node_id = NodeId(sid)
        if (
            isinstance(start, int)
            and isinstance(end, int)
            and start >= 1
            and end >= start
        ):
            for line_num in range(start, end + 1):
                mapping[line_num] = node_id
            continue
        if isinstance(line_no, int) and line_no >= 1:
            mapping[line_no] = node_id
    return mapping


def _document_below_full_text_threshold(
    source_text: str,
    format_key: str,
    config: PreviewSelectorConfig,
) -> bool:
    """True when source line count is strictly below ``full_text_max_lines``."""
    threshold = config.full_text_max_lines.get(format_key, DEFAULT_FULL_TEXT_MAX_LINES)
    if threshold <= 0 or not source_text.strip():
        return False
    return compute_line_span(source_text) < threshold


def _full_tree_block_set(tree: Any) -> list[Any]:
    """All nodes in short_id order (small-document root view)."""
    return sorted(
        list(_iter_all_nodes(tree)),
        key=lambda n: int(getattr(n, "short_id", 0)),
    )


def _selector_omitted(raw_selector: object) -> bool:
    """Return selector omitted."""
    return raw_selector is None or raw_selector == "" or raw_selector == []


def _root_view_block_set(
    tree: Any,
    navigation: PreviewNavigation,
    focus_short_id: NodeId,
) -> list[Any]:
    """Blocks for omitted node_ref.

    Single-container trees (JSON/YAML object root): children of that root.
    Multi-root trees (Python module statements): all top-level document nodes.
    """
    doc_blocks = _document_level_blocks(tree)
    if len(doc_blocks) > 1:
        return doc_blocks
    try:
        children = navigation._enumerate_children(tree, focus_short_id)
    except PreviewNavigationError:
        children = []
    if children:
        return children
    return doc_blocks


def _enrich_focus_for_root_view(
    focus_node: Node,
    *,
    tree: Any,
    source_text: str,
    format_key: str,
    budget: PreviewBudget,
    config: PreviewSelectorConfig,
    preview_abs_path: Path,
    max_short_id: int,
) -> None:
    """Populate ``focus.text`` / ``attributes.full_text`` for root_view."""
    attrs = dict(focus_node.attributes or {})
    threshold = config.full_text_max_lines.get(format_key, DEFAULT_FULL_TEXT_MAX_LINES)
    if threshold <= 0 or not source_text.strip():
        return
    if compute_line_span(source_text) >= threshold:
        return
    line_map = _document_line_to_short_id(tree)
    annotated = apply_line_id_prefixes(
        source_text,
        line_map,
        mode=PreviewTextMode.ANNOTATED,
        max_short_id=max_short_id,
    )
    attrs["text"] = annotated
    attrs["full_text"] = True
    focus_node.attributes = attrs


def navigate_degraded_as_text(
    params: dict[str, Any],
    budget: PreviewBudget,
    *,
    parse_error: str,
) -> NavigationResult | PreviewError:
    """Preview unparseable source as text format (paragraph/line tree + thresholds)."""
    preview_abs_path = Path(str(params["file_path"]))
    source_text = _read_source_text(preview_abs_path=preview_abs_path)
    from code_analysis.tree.handlers.text_handler import TextHandler

    nodes = TextHandler().parse_content(preview_abs_path, source_text)
    if not nodes:
        invalid = invalid_source_node(
            str(preview_abs_path),
            ValueError(parse_error),
        )
        return NavigationResult(
            focus_node=invalid,
            total_blocks=0,
            selected_blocks=[],
            tree_id=None,
            short_id_refs=True,
        )
    tree = NodeListTree(nodes)

    def _static_loader(_source_path: Path, _session_id: str | None) -> NodeListTree:
        """Return static loader."""
        return tree

    result = _navigate_loaded_tree(
        params,
        budget,
        tree=tree,
        loader=_static_loader,
        preview_abs_path=preview_abs_path,
        format_key="text",
        session_id=params.get("session_id"),
    )
    if isinstance(result, PreviewError):
        return result
    focus = result.focus_node
    focus.is_invalid = True
    attrs = dict(focus.attributes or {})
    attrs["parse_error"] = parse_error
    focus.attributes = attrs
    return NavigationResult(
        focus_node=focus,
        total_blocks=result.total_blocks,
        selected_blocks=result.selected_blocks,
        tree_id=result.tree_id,
        short_id_refs=result.short_id_refs,
    )


def _navigate_loaded_tree(
    params: dict[str, Any],
    budget: PreviewBudget,
    *,
    tree: Any,
    loader: Any,
    preview_abs_path: Path,
    format_key: str,
    session_id: str | None,
) -> NavigationResult | PreviewError:
    """Run root/drill preview on an already-loaded marked tree."""
    root_view = normalize_optional_node_ref(params.get("node_ref")) is None
    try:
        focus_short_id = parse_focus_short_id(params.get("node_ref"), tree.nodes)
    except ValueError as exc:
        return input_error(
            INPUT_ERROR_UNKNOWN_NODE_REF,
            str(exc),
            details={"node_ref": params.get("node_ref")},
        )

    raw_selector = params.get("selector")
    config = PreviewSelectorConfig(
        full_text_max_lines={format_key: budget.full_text_max_lines},
    )
    navigation = PreviewNavigation(tree_loader=loader)
    max_short_id = compute_max_short_id_in_tree(tree)
    source_text = _read_source_text(preview_abs_path=preview_abs_path)
    small_document = root_view and _document_below_full_text_threshold(
        source_text,
        format_key,
        config,
    )
    if small_document and _selector_omitted(raw_selector):
        selector: str | list[int] | None = None
    elif raw_selector is None:
        selector = f"0:{budget.preview_lines}"
    else:
        selector = raw_selector

    try:
        if root_view:
            if small_document and _selector_omitted(raw_selector):
                block_set = _full_tree_block_set(tree)
            else:
                block_set = _root_view_block_set(tree, navigation, focus_short_id)
            parsed = PreviewSelector.parse(selector)
            selected = parsed.apply(block_set)
            selected_blocks = [
                _preview_block_record_to_block(
                    navigation._render_block(
                        block,
                        format_key=format_key,
                        config=config,
                        text_mode=PreviewTextMode.ANNOTATED,
                        source_path=preview_abs_path,
                        max_short_id=max_short_id,
                    )
                )
                for block in selected
            ]
            total_blocks = len(block_set)
        else:
            result = navigation.navigate(
                source_path=preview_abs_path,
                focus_short_id=focus_short_id,
                selector=selector,
                session_id=session_id,
                config=config,
                text_mode=PreviewTextMode.ANNOTATED,
            )
            selected_blocks = [_preview_block_record_to_block(b) for b in result.blocks]
            total_blocks = len(navigation._enumerate_children(tree, focus_short_id))
    except PreviewNavigationError as exc:
        return input_error(
            INPUT_ERROR_UNKNOWN_NODE_REF,
            str(exc),
            details={"node_ref": params.get("node_ref")},
        )
    except PreviewSelectorError as exc:
        return input_error(
            INPUT_ERROR_INVALID_SELECTOR_FORM,
            str(exc),
            details={"selector": raw_selector},
        )

    _, by_short_id, _ = _build_indexes(tree)
    focus_node_raw = by_short_id.get(focus_short_id)
    if focus_node_raw is None:
        return input_error(
            INPUT_ERROR_UNKNOWN_NODE_REF,
            f"unknown short_id: {focus_short_id!r}",
            details={"node_ref": params.get("node_ref")},
        )
    focus_node = _tree_node_to_preview_node(focus_node_raw)
    if root_view:
        _enrich_focus_for_root_view(
            focus_node,
            tree=tree,
            source_text=source_text,
            format_key=format_key,
            budget=budget,
            config=config,
            preview_abs_path=preview_abs_path,
            max_short_id=max_short_id,
        )
    return NavigationResult(
        focus_node=focus_node,
        total_blocks=total_blocks,
        selected_blocks=selected_blocks,
        tree_id=None,
        short_id_refs=True,
    )


def navigate_marked_tree(
    params: dict[str, Any],
    budget: PreviewBudget,
) -> NavigationResult | PreviewError:
    """Run PreviewNavigation with TreeLifecycle-backed tree_loader."""
    project_root = Path(str(params["project_root"]))
    rel_file_path = str(params["rel_file_path"])
    preview_abs_path = Path(str(params["file_path"]))
    session_id = params.get("session_id")
    if session_id is not None:
        session_id = str(session_id)

    loader = make_preview_tree_loader(
        project_root=project_root,
        rel_file_path=rel_file_path,
        preview_abs_path=preview_abs_path,
        bound_session_id=session_id,
    )
    try:
        tree = loader(preview_abs_path, session_id)
    except Exception as exc:
        return navigate_degraded_as_text(params, budget, parse_error=str(exc))
    format_key = format_key_from_extension(preview_abs_path.suffix)
    return _navigate_loaded_tree(
        params,
        budget,
        tree=tree,
        loader=loader,
        preview_abs_path=preview_abs_path,
        format_key=format_key,
        session_id=session_id,
    )
