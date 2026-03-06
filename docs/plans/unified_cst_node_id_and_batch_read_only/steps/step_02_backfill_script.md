# Step 02 - Backfill existing entity rows

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** Data migration developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`scripts/backfill_entity_cst_node_id.py`

## Goal

Implement one-off backfill script that fills nullable `cst_node_id` for existing `classes/functions/methods` rows.

## Required behavior

- Resolve entity -> CST node mapping where possible.
- Write valid UUID4 in `cst_node_id`.
- If mapping is impossible, generate UUID4 using documented policy.

## Blackstops

- Do not leave NULL values after script completion.
- Do not write non-UUID4 values.
- Do not modify unrelated tables.

## Success metric

- Script reports processed, mapped, generated, and failed counters.
- Post-check confirms no NULL `cst_node_id` rows remain in target tables.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Re-run script in dry-run/test mode and validate output summary.
