# Parallel Execution Chains

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [PLAN.md](PLAN.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Rules

- A step can run in parallel only if all its declared dependencies are completed.
- Each step still follows "1 step = 1 code file = 1 step description file".
- Every parallel branch must execute full re-checks (code_mapper, black, flake8, mypy) before merge.

---

## Chain layout

### Phase A (strict sequence)

- Step 01 -> Step 02 -> Step 03 -> Step 04

### Phase B (parallel branch set after Step 04)

- **Branch B1:** Step 05
- **Branch B2:** Step 06
- **Branch B3:** Step 07

### Phase C (strict sequence after Phase B completion)

- Step 08

---

## Synchronization points

- Sync-1: Before Phase B, Step 04 must be complete and validated.
- Sync-2: Before Step 08, branches B1/B2/B3 must be complete and validated.
- Sync-3: Before handoff, final gate from `PLAN.md` must be complete.
