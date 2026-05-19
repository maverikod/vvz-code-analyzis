"""
YamlFileHandler — FileHandler for .yaml, .yml files (C-020).

Root NodeKind depends on the top-level YAML value:
  mapping  -> mapping
  sequence -> sequence
  scalar   -> scalar
YAML anchors and aliases are resolved before producing the node tree.
Identifier source:
  YAML tree index (JSON Pointer paths, stable node_id / uuid5 of pointer).
  JSON-pointer-style path traversal when resolving by path string.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from typing import Any

from ....core.yaml_tree.models import YamlTree
from ....core.yaml_tree.resolve import resolve_yaml_node
from ....core.yaml_tree.tree_builder import build_yaml_tree_from_data

from ..base_handler import FileHandler
from ..budget import PreviewBudget
from ..errors import (
    INPUT_ERROR_UNKNOWN_NODE_REF,
    PreviewError,
    file_structure_error,
    input_error,
)
from ..models import Node, NodeKind


class YamlFileHandler(FileHandler):
    """
    FileHandler for YAML files (.yaml, .yml) (C-020).

    Root NodeKind: mapping, sequence, or scalar.
    Anchors and aliases resolved before tree production.
        node_ref: JSON-pointer-style path (``""``, ``/key``) or opaque node_id
        from list_yaml_blocks (stable id for the path).

        Attributes:
            supported_extensions: frozenset({'.yaml', '.yml'}).
    """

    def _try_infra_resolve(
        self,
        node_ref: str,
        session: Any | None,
    ) -> "Node | PreviewError | None":
        """
        Resolve via in-memory :class:`~code_analysis.core.yaml_tree.models.YamlTree`.

        Returns a Node or PreviewError when ``session`` is a registered tree;
        None when the session is not a YAML tree (caller uses pointer fallback).
        """
        if session is None or not isinstance(session, YamlTree):
            return None
        value = resolve_yaml_node(session, node_ref)
        if value is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"YAML tree infra could not resolve {node_ref!r}.",
                details={"node_ref": node_ref},
            )
        if node_ref == "" or node_ref.startswith("/"):
            canon = node_ref
        else:
            canon = session.pointer_by_id.get(node_ref)
            if canon is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    f"Opaque node_ref {node_ref!r} has no pointer in tree session.",
                    details={"node_ref": node_ref},
                )
        return _yaml_value_to_node(value, canon)

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Frozenset of lowercase extensions this handler supports."""
        return frozenset({".yaml", ".yml"})

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        """Parse the YAML file and return the root Node.

        Root NodeKind is mapping, sequence, or scalar depending on the
        top-level YAML value. Anchors and aliases are resolved. On invalid
        YAML returns FILE_STRUCTURE_ERROR with parser 'yaml'.

        When *budget* is provided and ``budget.full_text_max_lines`` is a
        positive integer, and the file has fewer lines than that threshold,
        returns a ``NodeKind.SCALAR`` node whose ``value`` attribute holds
        the entire raw file source.  This mirrors the C-023 full-text
        fallback implemented for the Python and Markdown handlers.

        Args:
            file_path: Project-relative path to the .yaml/.yml file.
            session: :class:`~code_analysis.core.yaml_tree.models.YamlTree` or None.
            budget: Optional PreviewBudget; when provided, full_text_max_lines
                    is honoured.

        Returns:
            Root Node or PreviewError.
        """
        try:
            import yaml  # PyYAML

            self._last_file_path = file_path
            resolved_path = str(Path(file_path).resolve())

            if session is not None and isinstance(session, YamlTree):
                doc = session.root_data
                self._doc = doc
                self._pointer_by_node_id = dict(session.pointer_by_id)
                return _yaml_value_to_node(doc, "")

            raw = Path(file_path).read_text(encoding="utf-8", errors="replace")

            # full-text fallback (C-023) — same contract as Python/Markdown handlers.
            if (
                budget is not None
                and budget.full_text_max_lines > 0
                and raw.count("\n") + (1 if raw and not raw.endswith("\n") else 0)
                < budget.full_text_max_lines
            ):
                return Node(
                    node_kind=NodeKind.SCALAR,
                    node_ref="",
                    attributes={"value": raw, "full_text": True},
                )

            doc = yaml.safe_load(raw)
            if doc is None:
                doc = {}
            self._doc = doc
            tree = build_yaml_tree_from_data(resolved_path, doc, register=False)
            self._pointer_by_node_id = dict(tree.pointer_by_id)
            return _yaml_value_to_node(doc, "")
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            line = (mark.line + 1) if mark else None
            return file_structure_error(
                parser="yaml",
                message=str(exc),
                line_start=line,
                line_end=line,
            )
        except Exception as exc:
            return file_structure_error(parser="yaml", message=str(exc))

    def resolve_node_ref(
        self,
        node_ref: str,
        session: Any | None,
    ) -> Node | PreviewError:
        """
        Resolve a JSON Pointer or opaque node_id to the addressed YAML Node.

        Same rules as ``JsonFileHandler`` / ``list_yaml_blocks`` indexing.

        Args:
            node_ref: JSON Pointer or node_id string.
            session: Ignored for resolution (index is from ``open_root``).

        Returns:
            Resolved Node or PreviewError(UNKNOWN_NODE_REF).
        """
        doc = getattr(self, "_doc", None)
        if doc is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                "open_root must be called before resolve_node_ref.",
                details={"node_ref": node_ref},
            )
        if node_ref == "" or node_ref.startswith("/"):
            result = _resolve_yaml_pointer(doc, node_ref)
            if result is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    f"Path {node_ref!r} does not exist in YAML document.",
                    details={"node_ref": node_ref},
                )
            value, pointer = result
            return _yaml_value_to_node(value, pointer)
        ptr_map_raw = getattr(self, "_pointer_by_node_id", None)
        pointer_map: dict[str, str] = dict(ptr_map_raw) if ptr_map_raw else {}
        pointer_opt = pointer_map.get(node_ref)
        if pointer_opt is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"Unknown node_ref {node_ref!r}: not a JSON Pointer in this document "
                "and not a listed node_id.",
                details={"node_ref": node_ref},
            )
        result = _resolve_yaml_pointer(doc, pointer_opt)
        if result is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"node_id {node_ref!r} mapped to stale pointer {pointer_opt!r}; "
                "re-open the preview.",
                details={"node_ref": node_ref},
            )
        value, canon_pointer = result
        return _yaml_value_to_node(value, canon_pointer)


def _yaml_value_to_node(value: Any, pointer: str) -> Node:
    """Convert a YAML value to a preview Node with JSON-pointer path as node_ref."""
    if isinstance(value, dict):

        def _load_mapping() -> list[Node]:
            return [
                Node(
                    node_kind=NodeKind.MAPPING,
                    node_ref=f"{pointer}/{k}",
                    name=str(k),
                    attributes={"value_kind": type(v).__name__},
                )
                for k, v in value.items()
            ]

        return Node(
            node_kind=NodeKind.MAPPING,
            node_ref=pointer,
            _children_loader=_load_mapping,
        )
    if isinstance(value, list):

        def _load_seq() -> list[Node]:
            return [
                _yaml_value_to_node(v, f"{pointer}/{i}") for i, v in enumerate(value)
            ]

        return Node(
            node_kind=NodeKind.SEQUENCE,
            node_ref=pointer,
            _children_loader=_load_seq,
        )
    return Node(
        node_kind=NodeKind.SCALAR,
        node_ref=pointer,
        attributes={"value": str(value)},
    )


def _resolve_yaml_pointer(doc: Any, pointer: str) -> tuple[Any, str] | None:
    """Traverse YAML doc following JSON-pointer-style path."""
    if pointer == "":
        return (doc, "")
    if not pointer.startswith("/"):
        return None
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer[1:].split("/")]
    current: Any = doc
    path: str = ""
    for part in parts:
        path = f"{path}/{part}"
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                try:
                    current = current[int(part)]
                except (ValueError, KeyError, TypeError):
                    return None
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return (current, path)
