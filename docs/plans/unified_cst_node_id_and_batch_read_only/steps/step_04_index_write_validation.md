# Step 04 - Write-path UUID4 validation and persistence

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** Core indexing developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/core/database/files.py`

## Goal

Persist `cst_node_id` on entity writes and enforce fail-fast UUID4 validation before insert/update.

## Required behavior

- Map Class/Function/Method entities to CST node IDs.
- Persist `cst_node_id` during indexing writes.
- Reject missing/empty/invalid UUID4 with explicit error.

## Blackstops

- No line/range as primary identity for write target.
- No silent fallback values.
- No write with invalid `cst_node_id`.

## Success metric

- Entity writes always contain valid UUID4 `cst_node_id`.
- Invalid values fail with clear error message.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Re-run indexing scenario and verify stored IDs and errors.
