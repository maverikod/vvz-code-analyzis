"""
Perform superclass extraction (source slicing, base + children code).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List


def perform_extraction(
    extractor: Any,
    config: Dict[str, Any],
    child_nodes: List[ast.ClassDef],
) -> str:
    """
    Perform the actual superclass extraction using source slicing.
    Avoids ast.unparse for the module rewrite to preserve comments.
    """
    if not extractor.tree:
        raise ValueError("AST tree not loaded")
    base_class_name = config.get("base_class")
    extract_from = config.get("extract_from", {})
    abstract_methods = config.get("abstract_methods", []) or []
    module_lines = extractor.original_content.split("\n")

    start = min(c.lineno for c in child_nodes) - 1 if child_nodes else 0
    end = (
        max(
            (
                c.end_lineno
                if hasattr(c, "end_lineno") and c.end_lineno
                else extractor._find_class_end(c, module_lines)
            )
            for c in child_nodes
        )
        if child_nodes
        else 0
    )

    before = "\n".join(module_lines[:start]).rstrip("\n")
    after = "\n".join(module_lines[end:]).lstrip("\n")

    base_indent = 0
    class_indent = " " * base_indent
    indent = class_indent + "    "

    abc_import_line = "from abc import ABC, abstractmethod"
    if abstract_methods:
        if abc_import_line not in before and "import abc" not in before:
            header_lines = before.split("\n") if before else []
            insert_at = 0
            for i, line in enumerate(header_lines):
                if line.startswith("import ") or line.startswith("from "):
                    insert_at = i + 1
            header_lines.insert(insert_at, abc_import_line)
            before = "\n".join(header_lines).rstrip("\n")

    base_decl = (
        f"{class_indent}class {base_class_name}(ABC):"
        if abstract_methods
        else f"{class_indent}class {base_class_name}:"
    )
    base_lines: list[str] = [base_decl]
    base_lines.append(f'{indent}"""Base class with common functionality."""')

    all_props: set[str] = set()
    for child_config in extract_from.values():
        all_props.update(child_config.get("properties", []))
        all_props.update(child_config.get("props", []))
    if all_props:
        base_lines.append(f"{indent}def __init__(self):")
        init_indent = indent + "    "
        for prop in sorted(all_props):
            base_lines.append(f"{init_indent}self.{prop} = None")

    all_methods: set[str] = set()
    for child_config in extract_from.values():
        all_methods.update(child_config.get("methods", []))

    for method_name in sorted(all_methods):
        method_node = None
        for child in child_nodes:
            method_node = extractor._find_method_in_class(child, method_name)
            if method_node:
                break
        if not method_node:
            continue
        if method_name in abstract_methods:
            base_lines.append(f"{indent}@abstractmethod")
            extracted = extractor._extract_method_code(method_node, indent)
            header = None
            for line in extracted.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("def ") or stripped.startswith("async def "):
                    header = indent + stripped
                    break
            if header is None:
                header = f"{indent}def {method_name}(self):"
            base_lines.append(header)
            base_lines.append(f"{indent}    raise NotImplementedError")
        else:
            method_code = extractor._extract_method_code(method_node, indent)
            if method_code.strip():
                base_lines.append(method_code)

    base_code = "\n".join(base_lines)

    updated_children: list[str] = []
    for child_node in child_nodes:
        updated_children.append(
            f"{class_indent}class {child_node.name}({base_class_name}):"
        )
        child_doc = ast.get_docstring(child_node)
        if child_doc:
            updated_children.append(f'{indent}"""{child_doc}"""')
        updated_children.append(f"{indent}pass")

    new_block = "\n\n".join([base_code] + updated_children)

    parts: list[str] = []
    if before.strip():
        parts.append(before)
    parts.append(new_block)
    if after.strip():
        parts.append(after)
    return "\n\n".join(parts).rstrip() + "\n"
