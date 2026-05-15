"""
JsonFileHandler — FileHandler for .json files (C-018).

Root NodeKind depends on the top-level JSON value:
  dict   -> mapping
  list   -> sequence
  scalar -> scalar
Identifier source: node_id from list_json_blocks OR JSON Pointer string.
Lazy materialisation: only root and requested children are produced.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ....core.json_tree.tree_builder import build_tree_from_data

from ..base_handler import FileHandler
from ..budget import PreviewBudget
from ..errors import (
    INPUT_ERROR_UNKNOWN_NODE_REF,
    PreviewError,
    file_structure_error,
    input_error,
)
from ..models import Node, NodeKind

logger = logging.getLogger(__name__)


class JsonFileHandler(FileHandler):
    """
    FileHandler for JSON files (.json) (C-018).

        Root NodeKind: mapping (object), sequence (array), or scalar.
        Identifier source: JSON Pointer (RFC 6901) or opaque node_id from
        list_json_blocks (same index as TreeSession metadata).
        Lazy materialisation: only root and needed children are produced.
    FILE_STRUCTURE_ERROR on invalid JSON with parser name 'json'.

    Attributes:
        supported_extensions: frozenset({'.json'}).
    """

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".json"})

    def open_root(
        self,
        file_path: str,
        session: Any | None,
        budget: PreviewBudget | None = None,
    ) -> Node | PreviewError:
        """
        Parse the JSON file and return the root Node.

        Root NodeKind is mapping, sequence, or scalar depending on the
        top-level JSON value type. On invalid JSON returns FILE_STRUCTURE_ERROR.

        Args:
            file_path: Project-relative path to the .json file.
            session: Existing JSON TreeSession or None.

        Returns:
            Root Node or PreviewError.
        """
        try:
            self._last_file_path = file_path
            if session is not None:
                doc = session  # assume session is the parsed object
            else:
                raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
                doc = json.loads(raw)
            self._doc = doc
            # Same node_id ⇄ JSON Pointer mapping as list_json_blocks / JSONTree.
            self._pointer_by_node_id = dict(
                build_tree_from_data(
                    str(Path(file_path).resolve()),
                    doc,
                    register=False,
                ).pointer_by_id
            )
            return _json_value_to_node(doc, "")
        except json.JSONDecodeError as exc:
            return file_structure_error(
                parser="json",
                message=str(exc),
                line_start=exc.lineno,
                line_end=exc.lineno,
            )
        except Exception as exc:
            return file_structure_error(parser="json", message=str(exc))

    def resolve_node_ref(
        self,
        node_ref: str,
        session: Any | None,
    ) -> Node | PreviewError:
        """
        Resolve a JSON Pointer or node_id to the addressed JSON Node.

        Accepts either a JSON Pointer string (RFC 6901: '', '/foo', '/a/0/b')
        or an opaque node_id string from list_json_blocks (treated as JSON
        Pointer if it starts with '/', else looked up in _doc index).

        Args:
            node_ref: JSON Pointer or node_id string.
            session: JSON TreeSession or None.

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
        # Dispatch: JSON Pointer strings start with '/' or are the empty string.
        if node_ref == "" or node_ref.startswith("/"):
            result = _resolve_json_pointer(doc, node_ref)
            if result is None:
                return input_error(
                    INPUT_ERROR_UNKNOWN_NODE_REF,
                    f"JSON Pointer {node_ref!r} does not exist in document.",
                    details={"node_ref": node_ref},
                )
            value, pointer = result
            return _json_value_to_node(value, pointer)
        # Opaque node_id (matches list_json_blocks): resolve via open-time index.
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
        result = _resolve_json_pointer(doc, pointer_opt)
        if result is None:
            return input_error(
                INPUT_ERROR_UNKNOWN_NODE_REF,
                f"node_id {node_ref!r} mapped to stale pointer {pointer_opt!r}; "
                "re-open the preview.",
                details={"node_ref": node_ref},
            )
        value, canon_pointer = result
        return _json_value_to_node(value, canon_pointer)


def _json_value_to_node(value: Any, pointer: str) -> Node:
    """Convert a JSON value to a preview Node with JSON Pointer as node_ref."""
    if isinstance(value, dict):

        def _load_mapping() -> list[Node]:
            return [
                _json_pair_to_node(k, v, f"{pointer}/{k}") for k, v in value.items()
            ]

        return Node(
            node_kind=NodeKind.MAPPING,
            node_ref=pointer,
            _children_loader=_load_mapping,
        )
    if isinstance(value, list):

        def _load_seq() -> list[Node]:
            return [
                _json_value_to_node(v, f"{pointer}/{i}") for i, v in enumerate(value)
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


def _json_pair_to_node(key: str, value: Any, pointer: str) -> Node:
    """One mapping key-value pair as a single Block Node."""
    return Node(
        node_kind=NodeKind.MAPPING,
        node_ref=pointer,
        name=key,
        attributes={"value_kind": type(value).__name__},
    )


def _resolve_json_pointer(doc: Any, pointer: str) -> tuple[Any, str] | None:
    """Traverse doc following RFC-6901 pointer; return (value, pointer) or None."""
    if pointer == "":
        return (doc, "")
    if not pointer.startswith("/"):
        return None  # invalid pointer (non-RFC-6901 strings handled as None)
    parts = pointer[1:].split("/")
    parts = [p.replace("~1", "/").replace("~0", "~") for p in parts]
    current = doc
    path = ""
    for part in parts:
        path = f"{path}/{part}"
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return (current, path)
