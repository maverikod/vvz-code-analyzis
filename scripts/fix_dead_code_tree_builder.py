"""Remove a known dead-code fragment from the CST tree builder."""

import pathlib

path = pathlib.Path(
    "/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/cst_tree/tree_builder.py"
)
src = path.read_text(encoding="utf-8")
old = "    if persisted_node_ids:\n        exact_key_to_id.update(persisted_node_ids)\n"
if old in src:
    path.write_text(src.replace(old, "", 1), encoding="utf-8")
    print("Done: removed dead code")
else:
    print("ERROR: pattern not found")
    print(
        repr(
            src[
                src.find("persisted_node_ids")
                - 20 : src.find("persisted_node_ids")
                + 80
            ]
        )
    )
