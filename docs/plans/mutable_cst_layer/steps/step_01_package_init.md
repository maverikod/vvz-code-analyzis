# Step 01 — Package init

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Plan:** [../PLAN.md](../PLAN.md) · **TZ:** [../MUTABLE_CST_LAYER_TZ.md](../MUTABLE_CST_LAYER_TZ.md)

---

## Deliverable

New package under `code_analysis/core/` named `mutable_cst` (or `cst_mutable_layer`; keep consistent in all steps).

## Output file

`code_analysis/core/mutable_cst/__init__.py`

- Module docstring (Author, email).
- Export public types/functions that will be used by `tree_modifier` (e.g. `MutableTree`, `build_from_libcst`, `apply_operations`, `serialize_to_source` — exact names after you define them in later steps).
- No logic beyond imports and `__all__`.

## Success metric

- `from code_analysis.core.mutable_cst import ...` runs without import errors.
- `code_mapper -r code_analysis`, `black`, `flake8`, `mypy` on this file pass.

## Mandatory checks after step

See [../PLAN.md](../PLAN.md) (section «Mandatory checks after each code step»): fix incomplete code, TODO, `...`, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations; then `code_mapper -r code_analysis`, black, flake8, mypy.

## Links

- **TZ:** [§3.2 Implementation](../MUTABLE_CST_LAYER_TZ.md#32-implementation-code)
- **Previous:** [Step 00 — Design document](step_00_design.md)
- **Next:** [Step 02 — Mutable node and tree model](step_02_models.md)
