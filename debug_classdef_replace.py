"""Debug ClassDef replace bug."""
import sys

from code_analysis.core.cst_tree.tree_builder import load_file_to_tree
from code_analysis.core.cst_tree.tree_modifier_ops_find import (
    find_node_in_module_by_position,
    resolve_replace_target_to_current_module,
    _node_is_in_module_tree,
)

FILE = 'code_analysis/commands/cst_load_file_command.py'
tree = load_file_to_tree(FILE)

class_meta = None
for nid, meta in tree.metadata_map.items():
    if meta.type == 'ClassDef' and meta.name == 'CSTLoadFileCommand':
        class_meta = meta
        break

print(f'ClassDef: start={class_meta.start_line},{class_meta.start_col} end={class_meta.end_line},{class_meta.end_col}')

found = find_node_in_module_by_position(
    tree.module,
    class_meta.start_line, class_meta.start_col,
    class_meta.end_line, class_meta.end_col,
)
print(f'found type: {type(found).__name__ if found else None}')

if found:
    in_body = any(stmt is found for stmt in tree.module.body)
    print(f'found in module.body: {in_body}')
    in_tree = _node_is_in_module_tree(tree.module, found)
    print(f'_node_is_in_module_tree: {in_tree}')
    resolved = resolve_replace_target_to_current_module(tree.module, found, class_meta)
    print(f'resolved type: {type(resolved).__name__}')
    print(f'resolved is found: {resolved is found}')
    in_body2 = any(stmt is resolved for stmt in tree.module.body)
    print(f'resolved in module.body: {in_body2}')

print(f'module.body types: {[type(s).__name__ for s in tree.module.body]}')
