"""Inline stable-id lifecycle: strip @node-id comments from CST module and restore them before save.

Lifecycle:
  1. Load: parse file (comments present) -> _build_tree_index reads stable_id from leading_lines
             -> strip_inline_stable_ids(module) -> clean module in memory, stable_id safe in metadata_map
  2. Modify: model works with clean code, never sees @node-id comments
  3. Save: restore_inline_stable_ids(module, metadata_map) -> module with @node-id comments -> write to disk

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com"""

# cst-node-ids: begin
# cst-node-ids: version=2
# cst-node-ids: data={"0":"169451c3-855d-4d64-a53c-16eb9f404081","0.0":"1c8c2374-046c-4899-946d-ae0cd74095ac","0.0.0":"b5a6b109-0cec-4ce7-b2f8-8cd6fb84704b","0.0.0.0":"b369a941-eb87-4bf7-9a51-b9ca556f6ad2","0.0.1":"02924dee-d818-40a4-a6b8-386a53639844","0.0.1.0":"2a1680bd-ae8f-44b3-8afd-0c9ecf07fe2a","0.0.1.1":"57840ea1-6e29-4342-b1d6-b277f51a7a70"}
# cst-node-ids: end
