# Step 2: `cst_get_node_at_line` command (node + parent in one call)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Plan index:** [REFACTOR_PLAN.md](../REFACTOR_PLAN.md)

---

## Goal

Return the node spanning a given line and its parent in one response. Reduces round-trips (today: get_node_by_range + get_node_info with include_parent).

## File to add

`code_analysis/commands/cst_get_node_at_line_command.py`

## Behaviour

- Input: `tree_id`, `line` (1-based).
- Use existing `find_node_by_range(tree_id, line, line)` and `get_node_parent(tree_id, node_id)` from `code_analysis/core/cst_tree/`.
- Response: `node` (metadata dict), `parent` (metadata dict or null if root). Optionally `include_code` for node (and parent).
- If no node for line: clear error (e.g. NODE_NOT_FOUND or LINE_OUT_OF_RANGE).

## References

- Concept §6.6 “Node + parent in one call”: [CST_CONCEPT_AND_PIPELINE.md](../CST_CONCEPT_AND_PIPELINE.md)
- Gap analysis “Option C”: [CST_COMMANDS_GAP_ANALYSIS.md](../../analysis/CST_COMMANDS_GAP_ANALYSIS.md)

## Registration

Register in `code_analysis/hooks.py`.

## Success metrics

- For a loaded tree and valid line, response has `node` and `parent` (or parent null for module root).
- For line with no node / invalid tree_id: defined error, no crash.
- With `include_code=True`, node (and parent if present) include code snippet.

## Post-step checks

- Search and fix: incomplete code, TODO, ellipsis/syntax violations, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations from project/plan rules.
- Run `code_mapper -r <project_code_dir>` and fix all reported errors.
- Run `mypy`, `flake8`, `black` and fix all reported issues.
