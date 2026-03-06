# Step 05: Wire CST Save Flow to Unified Service

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Role

Senior Python command/persistence integrator.

## Target code file

`code_analysis/core/cst_tree/tree_saver.py`

## Goal

Ensure tree-save write path uses the same unified file-level DB sync implementation.

## Tasks

1. Replace flow-specific DB write internals with a call to unified file sync service.
2. Keep file-source-of-truth behavior.
3. Keep rollback/restore behavior semantics consistent with TZ.
4. Ensure success/failure is reported at full-file granularity.

## Acceptance checks

- `cst_save_tree` path calls unified service.
- No duplicate DB write logic remains in this flow.
- No partial-file success behavior.

## Blackstops

- Stop if this flow still requires separate per-entity DB writes.
- Stop if rollback semantics regress.
