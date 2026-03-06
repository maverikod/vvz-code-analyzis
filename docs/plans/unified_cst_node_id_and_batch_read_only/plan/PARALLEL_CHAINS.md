# Parallel execution chains

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [PLAN.md](PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Rules

- A step can run in parallel only if all its declared dependencies are completed.
- Each parallel step still follows "1 step = 1 code file = 1 step description file".
- Every parallel branch must execute full re-checks (code_mapper, black, flake8, mypy) before merge.

---

## Chain layout

### Phase A (strict sequence)

- Step 01 -> Step 02 -> Step 03 -> Step 04

### Phase B (parallel branch set after Step 04)

- **Branch B1:** Step 05 -> Step 06 -> Step 07
- **Branch B2:** Step 08 -> Step 09 -> Step 10 -> Step 11
- **Branch B3:** Step 12 -> Step 13
- **Branch B4:** Step 17 -> Step 18

### Phase C (strict sequence after Phase B completion)

- Step 14 -> Step 15 -> Step 16 -> Step 19

---

## Synchronization points

- Sync-1: Before starting Phase B, Step 04 must be complete and validated.
- Sync-2: Before starting Step 14, all branches B1/B2/B3/B4 must be complete and validated.
- Sync-3: Before final handoff, Steps 14-19 and final gate must be complete.
