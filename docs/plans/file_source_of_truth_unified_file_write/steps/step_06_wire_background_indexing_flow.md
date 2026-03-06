# Step 06: Wire Background Indexing to Unified Service

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Role

Senior Python worker/indexing integrator.

## Target code file

`code_analysis/commands/update_indexes_analyzer.py`

## Goal

Ensure background indexing uses the exact same file-level DB sync service as tree-save flow.

## Tasks

1. Route per-file indexing write to unified file sync service.
2. Remove/disable duplicate write implementation in analyzer flow.
3. Preserve existing worker-level behavior contracts where not conflicting with TZ.
4. Keep result contract explicit for file-level success/failure.

## Acceptance checks

- Background indexing path calls unified service.
- Call-path parity with tree-save flow is verifiable in tests.
- No residual bypass path for file DB write in this module.

## Blackstops

- Stop if analyzer retains independent DB write branch for full file sync.
- Stop if file-level failure can still be reported as success.
