# Step 04 — Edits (replace, insert, delete)

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Plan:** [../PLAN.md](../PLAN.md) · **TZ:** [../MUTABLE_CST_LAYER_TZ.md](../MUTABLE_CST_LAYER_TZ.md)

---

## Deliverable

In-place replace by node id, insert at position, delete node.

## Output file

`code_analysis/core/mutable_cst/edits.py`

- **Replace:** resolve node by id in the tree's map; replace its content or swap in parent's `children`; do not rebuild whole tree.
- **Insert:** by parent id and position (first/last/after index); modify parent's `children` in place.
- **Delete:** remove node from parent's `children` in place.
- Use `tree_modifier_ops.parse_code_snippet` for replace; `parse_code_snippet_or_comment` for insert when comment-only is allowed (see TZ §3.2).
- Operations must be applied in order sorted by `(end_line, end_col)` descending; caller or this module can sort.
- File/function docstrings: Author, email. No TODO, no `pass` outside exceptions.

## Success metric

Given a mutable tree, applying a list of operations (replace/insert/delete) sorted by (end_line, end_col) desc modifies the tree in place; no full-tree rebuild. Mandatory checks pass.

## Reference

`code_analysis/core/cst_tree/tree_modifier_ops.py` — `parse_code_snippet`, `parse_code_snippet_or_comment`.

## Mandatory checks after step

See [../PLAN.md](../PLAN.md) (section «Mandatory checks after each code step»): fix incomplete code, TODO, `...`, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations; then `code_mapper -r code_analysis`, black, flake8, mypy.

## Links

- **TZ:** [§3.2 Implementation](../MUTABLE_CST_LAYER_TZ.md#32-implementation-code) (Edits, Parsing new code)
- **Previous:** [Step 02 — Models](step_02_models.md), [Step 03 — Build](step_03_build.md)
- **Next:** [Step 05 — Serialization](step_05_serialize.md)
