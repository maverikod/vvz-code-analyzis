# Step 5: First-class `move` action and precise positioning in `cst_modify_tree`

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Plan index:** [REFACTOR_PLAN.md](../REFACTOR_PLAN.md)

---

## Goal

Support action **move** and **precise positioning** for insert/move: parent (or root sentinel), position by first/last or after sibling index. Insert vs move is determined by whether the node_id already exists in the tree. Write semantics: replace if same place; insert if new; if node exists but wrong parent/position, remove and insert.

## Files to modify

- `code_analysis/commands/cst_modify_tree_command.py` — accept action "move" and precise position semantics; accept `__root__` as parent.
- `code_analysis/core/cst_tree/tree_modifier.py` — implement move and position (first / last / after N).

## Behaviour

- **Root sentinel:** Parent can be the reserved **`__root__`** (exact spelling: `ROOT_NODE_ID_SENTINEL = "__root__"` in code) for module-level placement. If parent is omitted, treat as `__root__`.
- **Position:** For insert and move, position must be precisely specified:
  - **`first`** — insert/move as the first child of the parent.
  - **`last`** — insert/move as the last child of the parent (append).
  - **After index N** — insert/move after the sibling at 0-based index N within the parent. If N is out of range (e.g. no such sibling), treat as **last**.
- **Insert vs move:** The tool determines the semantics from the tree:
  - If a node with the given **node_id already exists** in the tree → **move** (change parent and/or position; keep content unless also replacing).
  - If **node_id does not exist** → **insert** (add new node with given code at parent + position).
- **Write (replace/upsert):** When the client sends a node (node_id + content):
  - If node **exists** and is already at the correct parent and position → **replace** its content (and descendants).
  - If node **does not exist** → **insert** at the given parent and position.
  - If node **exists but** parent or position is different → **remove** the node from its current place and **insert** it at the new parent/position with the given content.
- Operation shape: e.g. `{ "action": "move" | "insert", "node_id": "...", "parent_node_id": "..." | "__root__", "position": "first" | "last" | {"after": N}, "code" | "code_lines" (for insert) }`. Validation: node exists for move; parent/target exists; move is valid (e.g. not ancestor of itself). Apply atomically with other ops.

## References

- Concept §6.3 “Write: precise positioning”; §6.3a “Batch as operation language”; root sentinel `__root__`: [CST_CONCEPT_AND_PIPELINE.md](../CST_CONCEPT_AND_PIPELINE.md)

## Success metrics

- Single operation move: node content unchanged, position in tree changed to new parent + position (first/last/after N).
- Insert with parent `__root__` and position `first`/`last`/after N: node appears at correct place.
- Batch with move + replace/delete: all applied atomically; on any validation failure, tree unchanged.
- Invalid move (e.g. node is ancestor of new parent): clear error, no partial apply.

## Post-step checks

- Search and fix: incomplete code, TODO, ellipsis/syntax violations, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations from project/plan rules.
- Run `code_mapper -r <project_code_dir>` and fix all reported errors.
- Run `mypy`, `flake8`, `black` and fix all reported issues.
