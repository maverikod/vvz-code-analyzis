# Step 06 — Integration in tree_modifier

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Plan:** [../PLAN.md](../PLAN.md) · **TZ:** [../MUTABLE_CST_LAYER_TZ.md](../MUTABLE_CST_LAYER_TZ.md)

---

## Deliverable

Batch path in `modify_tree` uses mutable layer.

## Output file

`code_analysis/core/cst_tree/tree_modifier.py`

- When a **batch** is detected (e.g. more than one replace, or more than one insert, or any delete in the same call): get tree, validate ops, build mutable tree from `tree.module` with current `metadata_map`, sort ops by (end_line, end_col) desc, apply ops on mutable tree, serialize to source, parse to `cst.Module`, validate with `compile`, update `tree.module` and rebuild index via `_build_tree_index`.
- Single-op path: leave unchanged or route through mutable layer; behaviour must remain the same (no regression).
- REPLACE_RANGE / MOVE: either implement in mutable layer or keep current LibCST path for those op types only.
- Do not change function signature or return type of `modify_tree`.
- File/docstrings: Author, email. No TODO, no stray `pass`.

## Success metric

- `modify_tree(tree_id, [op1, op2])` with two replace ops (e.g. two methods in one class) succeeds and result compiles.
- Existing tests in `tests/test_tree_modifier.py` pass.
- Mandatory checks pass.

## Mandatory checks after step

See [../PLAN.md](../PLAN.md) (section «Mandatory checks after each code step»): fix incomplete code, TODO, `...`, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations; then `code_mapper -r code_analysis`, black, flake8, mypy.

## Links

- **TZ:** [§3.3 Integration](../MUTABLE_CST_LAYER_TZ.md#33-integration-with-current-flow)
- **Previous:** [Step 01](step_01_package_init.md) … [Step 05](step_05_serialize.md)
- **Next:** [Step 07 — Tests](step_07_tests.md)
