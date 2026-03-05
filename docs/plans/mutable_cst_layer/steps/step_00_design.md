# Step 00 — Design document

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Plan:** [../PLAN.md](../PLAN.md) · **TZ:** [../MUTABLE_CST_LAYER_TZ.md](../MUTABLE_CST_LAYER_TZ.md)

---

## Deliverable

One design document (no code).

## Output file

Either extend [../../MUTABLE_CST_LAYER_TASK.md](../../MUTABLE_CST_LAYER_TASK.md) with a "Design" section, or use `docs/plans/design/MUTABLE_CST_LAYER_DESIGN.md`. Content in English only: mutable node model, LibCST → mutable conversion, edit operations (replace/insert/delete, ordering), serialization to source (and optionally to LibCST). No code in the doc.

## Success metric

- Document exists.
- It describes node model, conversion, edits, and serialization in prose/schemas.
- No code blocks with implementation.

## Mandatory checks after step

See [../PLAN.md](../PLAN.md) (section «Mandatory checks after each code step»). This step produces only a doc; no code_mapper/black/flake8/mypy.

## Links

- **TZ:** [§3.1 Design document](../MUTABLE_CST_LAYER_TZ.md#31-design-document)
- **Next:** [Step 01 — Package init](step_01_package_init.md)
