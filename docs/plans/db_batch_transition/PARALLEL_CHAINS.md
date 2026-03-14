# Parallel chains: DB Batch Transition

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**TZ:** [TZ_DB_BATCH_TRANSITION.md](TZ_DB_BATCH_TRANSITION.md)  
**Plan:** [PLAN.md](PLAN.md)

---

## Wave 1 (parallel)

Steps in this wave do not depend on each other. They touch different files and different code paths. Execute in any order or concurrently (e.g. two executors in parallel).

| Step | Target file | Dependency |
|------|-------------|------------|
| step_01 | code_analysis/core/database/files/crud.py | None |
| step_02 | code_analysis/core/indexing_worker_pkg/processing.py | None |

**Rule:** Step 01 and Step 02 may be executed in parallel. No step depends on the other. Completion: both steps done and full test suite green.

---

## Validation after wave

After both steps are implemented, run from project root:

- `pytest`

All tests must pass. If any step was done in isolation, run `pytest` after that step; the plan is complete when Wave 1 is done and pytest is green.
