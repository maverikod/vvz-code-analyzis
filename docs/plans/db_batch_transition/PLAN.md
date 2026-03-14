# Plan: DB Batch Transition

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**TZ:** [TZ_DB_BATCH_TRANSITION.md](TZ_DB_BATCH_TRANSITION.md)  
**Parallel chains:** [PARALLEL_CHAINS.md](PARALLEL_CHAINS.md)

---

## Executor role

You are an executor (e.g. LLAMA). Implement exactly what is specified in the TZ and in the step file. Do not add architecture or alternatives. Read TZ, then this PLAN, then PARALLEL_CHAINS, then the step file and every "Read first" file in full before writing code. After code: run mandatory validation; step is complete only when the full test suite passes.

---

## Objective

Replace single-row DB writes with one batched write in two places: (1) clear_file_data in files/crud.py, (2) indexing cycle in indexing_worker_pkg/processing.py. Maximum parallelization: step 01 and step 02 are independent and can be executed in parallel or in any order.

---

## Execution policy

- One step = one target code file = one step file in `docs/plans/db_batch_transition/steps/`. Do not combine steps or change the target file of a step.
- Before changing code: read every file in the step's "Read first" in full. Read "Expected file change", "Forbidden alternatives", and "Blackstops" of that step.
- After code: run `black <target_file>`, `flake8 <target_file>`, `mypy <target_file>` from project root; then run `pytest`. Step is complete only when all tests pass.
- No alternative implementations. If a blackstop is met, stop and report.

---

## Step list (parallel wave)

| Step | Step file | Target code file | Purpose |
|------|-----------|------------------|---------|
| 01 | steps/step_01_clear_file_data_batch.md | code_analysis/core/database/files/crud.py | clear_file_data: build list of DELETE ops, run execute_batch(ops). |
| 02 | steps/step_02_indexing_cycle_batch.md | code_analysis/core/indexing_worker_pkg/processing.py | Accumulate indexing_errors and indexing_worker_stats per cycle; flush one batch at end of cycle. |

**Order:** Step 01 and Step 02 have no dependency on each other. Execute in any order or in parallel (see PARALLEL_CHAINS.md). Validation per step: from project root run `black <target_file>`, `flake8 <target_file>`, `mypy <target_file>`, `pytest`. Step complete only when all tests pass.

---

## Completion condition

- Both steps 01 and 02 implemented.
- Full test suite green (pytest from project root).
- clear_file_data performs all its DELETEs via one execute_batch (except any logic that must remain before the batch, e.g. _clear_file_vectors).
- Indexing cycle performs no per-file execute for indexing_errors or indexing_worker_stats; one batch at end of cycle.

---

## Decision rules (plan level)

- If a step says "modify only the target code file", do not modify any other file in that step.
- If validation fails, fix the target file and re-run until all pass; do not mark step complete until then.
- If in doubt, re-read the step's "Forbidden alternatives" and "Blackstops".

---

## Blackstops (plan level)

- Stop if you are about to change any file other than the step's target file.
- Stop if the step's blackstop condition is met; report and do not continue that step.

---

## References

- TZ: [TZ_DB_BATCH_TRANSITION.md](TZ_DB_BATCH_TRANSITION.md)
- Parallel order: [PARALLEL_CHAINS.md](PARALLEL_CHAINS.md)
- Step files: `docs/plans/db_batch_transition/steps/step_NN_*.md`
