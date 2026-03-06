# Step 12 - UUID4-only mutation target in cst_modify_tree

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** CST mutation command developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/cst_modify_tree_command.py`

## Goal

Make UUID4 node IDs the primary immutable mutation target reference for replace/insert/delete flows.

## Required behavior

- Validate incoming mutation target IDs as UUID4.
- Fail fast on missing/empty/invalid IDs.
- Keep non-ID selectors only as compatibility helper that must resolve to UUID4 before mutation.

## Blackstops

- No primary mutation by line/range.
- No silent fallback to positional targeting.

## Success metric

- Mutation commands operate on validated UUID4 targets and reject invalid input.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run positive/negative mutation tests.
