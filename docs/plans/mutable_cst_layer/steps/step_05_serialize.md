# Step 05 — Serialization

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Plan:** [../PLAN.md](../PLAN.md) · **TZ:** [../MUTABLE_CST_LAYER_TZ.md](../MUTABLE_CST_LAYER_TZ.md)

---

## Deliverable

Mutable tree → source code string; optionally → LibCST `Module`.

## Output file

`code_analysis/core/mutable_cst/serialize.py`

- `serialize_to_source(tree: MutableTree) -> str`: walk the tree, output each node's source (stored or generated), concatenate to full file string.
- Optionally: `to_libcst_module(tree: MutableTree) -> cst.Module` for validation/codegen.
- File/function docstrings: Author, email. No TODO, no `pass` outside exceptions.

## Success metric

- For a mutable tree built from a valid `cst.Module`, `serialize_to_source` returns a string that parses with `cst.parse_module` and `compile(..., "exec")` succeeds.
- If implemented, `to_libcst_module` returns a LibCST module equivalent for validation.
- Mandatory checks pass.

## Mandatory checks after step

See [../PLAN.md](../PLAN.md) (section «Mandatory checks after each code step»): fix incomplete code, TODO, `...`, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations; then `code_mapper -r code_analysis`, black, flake8, mypy.

## Links

- **TZ:** [§3.2 Implementation](../MUTABLE_CST_LAYER_TZ.md#32-implementation-code) (Serialization)
- **Previous:** [Step 02 — Models](step_02_models.md), [Step 04 — Edits](step_04_edits.md)
- **Next:** [Step 06 — Integration](step_06_integration.md)
