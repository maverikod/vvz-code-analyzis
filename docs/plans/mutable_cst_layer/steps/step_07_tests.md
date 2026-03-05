# Step 07 — Tests

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Plan:** [../PLAN.md](../PLAN.md) · **TZ:** [../MUTABLE_CST_LAYER_TZ.md](../MUTABLE_CST_LAYER_TZ.md)

---

## Deliverable

Unit tests for mutable layer and integration tests for batch modify_tree.

## Output file

`tests/test_mutable_cst_layer.py`

- **Unit tests:** build (build_from_libcst), replace, insert, delete, serialize (round-trip or equivalence).
- **Integration tests:** call `modify_tree` with multiple replace ops (e.g. N methods in one class); assert no "node not replaced" / "nodes were not inserted", result compiles, all edits present. Batch insert: multiple inserts in one call; assert all applied, result compiles.
- Use `create_tree_from_code`, `modify_tree`, `get_tree` from existing API; assert on `modified.module.code` and `compile(...)`.
- File/class docstrings: Author, email. No TODO in tests except documented skip reasons.

## Success metric

- All new tests pass.
- All tests in `tests/test_tree_modifier.py` pass (no regression).
- Mandatory checks pass.

## Mandatory checks after step

See [../PLAN.md](../PLAN.md) (section «Mandatory checks after each code step»): fix incomplete code, TODO, `...`, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations; then `code_mapper -r code_analysis`, black, flake8, mypy.

## Links

- **TZ:** [§3.4 Tests](../MUTABLE_CST_LAYER_TZ.md#34-tests)
- **Previous:** [Step 01](step_01_package_init.md) … [Step 06](step_06_integration.md)
