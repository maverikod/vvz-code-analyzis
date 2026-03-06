# Step 01 - Add nullable schema columns

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** Database schema developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/core/database/base.py`

## Goal

Add `cst_node_id` columns as nullable `TEXT` for `classes`, `functions`, `methods` in schema/init path.

## Blackstops

- Do not enforce `NOT NULL` in this step.
- Do not change existing primary keys/semantics.
- Do not add fallback behavior.

## Success metric

- New nullable columns are created for fresh DB initialization.
- Existing behavior not related to this column remains unchanged.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Re-read step and confirm exact scope only.
