# Step inspection report and split decisions

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [PLAN.md](PLAN.md)  
**Parallel map:** [PARALLEL_CHAINS.md](PARALLEL_CHAINS.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Inspection scope

- Reviewed all current step definitions in `../steps/`.
- Checked canonical constraints:
  - 1 step = 1 code file = 1 step description.
  - dependency consistency.
  - self-sufficiency and links.
  - mandatory parallel map.

---

## Findings

1. **Batch block was overloaded**
   - Previous Step 14 combined orchestration + whitelist semantics + output file serialization contract.
   - Risk: weak handoff granularity and blurred ownership.

2. **Plan links after relocation required normalization**
   - `steps/*.md` must reference plan in `../plan/PLAN.md`.

3. **Parallel map needed explicit branch for batch internals**
   - Whitelist and output storage logic can and should be developed in a separate branch before orchestration.

---

## Applied split

- Added **Step 17**: `read_only_batch_whitelist.py`.
- Added **Step 18**: `read_only_batch_output.py`.
- Added **Step 19**: `tests/test_read_only_batch_command.py`.
- Updated plan dependencies so Step 14 depends on Steps 17/18 and final verification is Step 19.
- Updated parallel chains with a new branch **B4** and final chain ending at Step 19.

---

## Result

- Granularity improved for high-risk batch functionality.
- Parallelization map is explicit and mandatory.
- Plan remains canonical and handoff-ready.
