# Step 03 — Build from LibCST

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Plan:** [../PLAN.md](../PLAN.md) · **TZ:** [../MUTABLE_CST_LAYER_TZ.md](../MUTABLE_CST_LAYER_TZ.md)

---

## Deliverable

Single-pass conversion LibCST `Module` → mutable tree with node_ids aligned to existing index.

## Output file

`code_analysis/core/mutable_cst/build.py`

- One main function, e.g. `build_from_libcst(module: cst.Module, metadata_map: Dict[str, TreeNodeMetadata]) -> MutableTree`.
- Use `MetadataWrapper` + `PositionProvider`; one walk; for each relevant node type (Module, ClassDef, FunctionDef, IndentedBlock, statement-level) create a mutable node and set parent/children/span.
- Assign each mutable node the same `node_id` as in `metadata_map` for the corresponding LibCST node (so existing UUIDs from `tree.metadata_map` resolve). Use the same or mirror logic of `tree_builder._build_tree_index` for which nodes get an id.
- File/function docstrings: Author, email. No placeholders, no TODO.

## Success metric

Given a `cst.Module` and its current `metadata_map`, `build_from_libcst` returns a `MutableTree` such that every key in `metadata_map` exists in the tree's node map and points to a node with matching span/type. Mandatory checks pass.

## Reference

`code_analysis/core/cst_tree/tree_builder.py` — `_build_tree_index`.

## Mandatory checks after step

See [../PLAN.md](../PLAN.md) (section «Mandatory checks after each code step»): fix incomplete code, TODO, `...`, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations; then `code_mapper -r code_analysis`, black, flake8, mypy.

## Links

- **TZ:** [§3.2 Implementation](../MUTABLE_CST_LAYER_TZ.md#32-implementation-code) (Build from LibCST)
- **Previous:** [Step 02 — Mutable node and tree model](step_02_models.md)
- **Next:** [Step 04 — Edits](step_04_edits.md)
