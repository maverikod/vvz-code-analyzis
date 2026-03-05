# Step 02 — Mutable node and tree model

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Plan:** [../PLAN.md](../PLAN.md) · **TZ:** [../MUTABLE_CST_LAYER_TZ.md](../MUTABLE_CST_LAYER_TZ.md)

---

## Deliverable

Mutable node type and tree wrapper with node_id → node map.

## Output file

`code_analysis/core/mutable_cst/models.py`

- One dataclass (or small class hierarchy) for a single mutable node: type, optional name, `parent`, `children`, span (`start_line`, `start_col`, `end_line`, `end_col`), stored source text or way to generate it; stable `node_id` (e.g. UUID).
- A thin tree type (e.g. wrapper or root node) that holds the root and a map `node_id → mutable node` for resolution.
- File/class docstrings: Author, email. No `pass` (except in exception bodies if any), no `NotImplemented` outside abstract methods, no TODO.

## Success metric

- Can instantiate a mutable node and a tree; tree can resolve a node by id.
- File ≤400 lines.
- Mandatory checks (see plan) pass.

## Mandatory checks after step

See [../PLAN.md](../PLAN.md) (section «Mandatory checks after each code step»): fix incomplete code, TODO, `...`, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations; then `code_mapper -r code_analysis`, black, flake8, mypy.

## Links

- **TZ:** [§3.2 Implementation](../MUTABLE_CST_LAYER_TZ.md#32-implementation-code) (node model, tree type)
- **Previous:** [Step 01 — Package init](step_01_package_init.md)
- **Next:** [Step 03 — Build from LibCST](step_03_build.md)
