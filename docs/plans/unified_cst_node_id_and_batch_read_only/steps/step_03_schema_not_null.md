# Step 03 - Enforce NOT NULL schema state

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** Database migration developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/core/database/schema_sync.py`

## Goal

Implement schema synchronization logic so final state enforces `cst_node_id TEXT NOT NULL` for `classes/functions/methods`.

## Blackstops

- Do not enforce NOT NULL before backfill is complete.
- Do not drop entity data during schema transition.
- Do not alter unrelated table constraints.

## Success metric

- Schema sync/migration reaches final NOT NULL state.
- Validation query confirms no NULL values and constraint is active.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Execute migration path test: nullable -> backfill -> NOT NULL.
