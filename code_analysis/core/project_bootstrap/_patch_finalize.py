"""Patch _finalize_cst_tree: fix TREE_MODULE_CORRUPT bug."""
import pathlib

path = pathlib.Path(
    '/home/vasilyvz/projects/tools/code_analysis'
    '/code_analysis/core/cst_tree/tree_builder.py'
)
content = path.read_text(encoding='utf-8')

old1 = (
    '                        _attach_disk_snapshot(tree, logical_source)\n'
    '                        # Strip inline/legacy markers from disk unconditionally\n'
    '                        if raw_disk_source != logical_source and py_path is not None:\n'
    '                            _strip_legacy_trailer_from_disk(py_path, logical_source)\n'
    '                    return'
)
new1 = (
    '                        # FIX: use tree.module.code (after strip_inline_stable_ids),\n'
    '                        # not logical_source. Inline @node-id markers removed by\n'
    '                        # strip_inline_stable_ids cause SHA mismatch -> TREE_MODULE_CORRUPT.\n'
    '                        _attach_disk_snapshot(tree, tree.module.code)\n'
    '                        # Strip inline/legacy markers from disk unconditionally\n'
    '                        if raw_disk_source != logical_source and py_path is not None:\n'
    '                            _strip_legacy_trailer_from_disk(py_path, logical_source)\n'
    '                    return'
)

old2 = (
    '        _attach_disk_snapshot(tree, logical_source)\n'
    '        # Strip inline/legacy markers from disk unconditionally (regardless of sidecar policy)\n'
    '        if raw_disk_source != logical_source and py_path is not None:\n'
    '            _strip_legacy_trailer_from_disk(py_path, logical_source)'
)
new2 = (
    '        # FIX: use tree.module.code (after strip_inline_stable_ids), not logical_source.\n'
    '        # Inline @node-id markers removed by strip_inline_stable_ids cause SHA mismatch\n'
    '        # -> TREE_MODULE_CORRUPT on next cst_modify_tree call.\n'
    '        _attach_disk_snapshot(tree, tree.module.code)\n'
    '        # Strip inline/legacy markers from disk unconditionally (regardless of sidecar policy)\n'
    '        if raw_disk_source != logical_source and py_path is not None:\n'
    '            _strip_legacy_trailer_from_disk(py_path, logical_source)'
)

assert old1 in content, f'Place 1 not found'
assert old2 in content, f'Place 2 not found'

content = content.replace(old1, new1, 1)
content = content.replace(old2, new2, 1)

path.write_text(content, encoding='utf-8')
print('OK: patched 2 places in tree_builder.py')
