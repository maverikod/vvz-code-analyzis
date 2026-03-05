# Step 4: Unify `children_depth` with string values "direct" | "recursive"

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Plan index:** [REFACTOR_PLAN.md](../REFACTOR_PLAN.md)

---

## Goal

Allow the same parameter that controls children depth to accept either an **integer** (0 = full subtree, 1 = direct only, 2+ = N levels) or a **string** `"direct"` | `"recursive"` for clarity. One parameter, two representations.

## File to modify

`code_analysis/commands/cst_get_node_info_command.py`

## Behaviour

- Use a **single parameter** (e.g. keep the name `children_depth` or rename to something that accepts both; if kept as `children_depth`): type `Union[int, str]` or equivalent in the schema.
  - **Integer:** `0` = full subtree (recursive), `1` = direct children only, `2`, `3`, … = up to N levels. Existing behaviour.
  - **String:** `"direct"` → same as 1; `"recursive"` → same as 0.
- When both an integer and a string could be passed (e.g. if introducing a separate `children_scope`), **do not** add a second parameter; instead allow the single parameter to accept either int or string. If the value is the string `"direct"` or `"recursive"`, map to depth 1 or 0; otherwise treat as integer.
- Schema: document that `children_depth` accepts integer (0, 1, 2, …) or string (`"direct"`, `"recursive"`). N levels expansion remains via integer only.

## References

- Concept §6.2 “Node request modes” (direct / N levels / whole branch): [CST_CONCEPT_AND_PIPELINE.md](../CST_CONCEPT_AND_PIPELINE.md)

## Success metrics

- include_children=True, children_depth="direct" (or 1) → only direct children.
- include_children=True, children_depth="recursive" (or 0) → full subtree.
- include_children=True, children_depth=2 → up to 2 levels (unchanged).
- Backward compatibility: existing integer usage unchanged.

## Post-step checks

- Search and fix: incomplete code, TODO, ellipsis/syntax violations, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations from project/plan rules.
- Run `code_mapper -r <project_code_dir>` and fix all reported errors.
- Run `mypy`, `flake8`, `black` and fix all reported issues.
