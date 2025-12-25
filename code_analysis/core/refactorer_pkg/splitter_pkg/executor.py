"""
Module executor.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)


def _perform_split(self, src_class: ast.ClassDef, config: Dict[str, Any]) -> str:
    """Perform the actual class splitting using AST."""
    if not self.tree:
        raise ValueError("AST tree not loaded")
    dst_classes = config.get("dst_classes", {})
    method_mapping: Dict[str, str] = {}
    prop_mapping: Dict[str, str] = {}
    for dst_class_name, dst_config in dst_classes.items():
        for method in dst_config.get("methods", []):
            method_mapping[method] = dst_class_name
        for prop in dst_config.get("props", []):
            prop_mapping[prop] = dst_class_name
    src_class_idx = None
    for i, node in enumerate(self.tree.body):
        if isinstance(node, ast.ClassDef) and node.name == src_class.name:
            src_class_idx = i
            break
    if src_class_idx is None:
        raise ValueError(f"Source class {src_class.name} not found in module body")
    new_class_nodes = []
    for dst_class_name, dst_config in dst_classes.items():
        new_class_node = self._build_new_class_ast(
            dst_class_name, src_class, dst_config
        )
        new_class_nodes.append(new_class_node)
    modified_src_class_node = self._build_modified_source_class_ast(
        src_class, method_mapping, prop_mapping, dst_classes
    )
    new_module_body = []
    new_module_body.extend(self.tree.body[:src_class_idx])
    new_module_body.append(modified_src_class_node)
    new_module_body.extend(new_class_nodes)
    new_module_body.extend(self.tree.body[src_class_idx + 1 :])
    new_module = ast.Module(body=new_module_body, type_ignores=[])
    return ast.unparse(new_module)
