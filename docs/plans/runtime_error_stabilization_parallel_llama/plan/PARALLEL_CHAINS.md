# Parallel Execution Chains

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [PLAN.md](PLAN.md)  
**TZ:** [../TZ_RUNTIME_ERROR_STABILIZATION_PARALLEL_LLAMA.md](../TZ_RUNTIME_ERROR_STABILIZATION_PARALLEL_LLAMA.md)

---

## Parallelization strategy (maximal safe split)

### Phase A (foundation)

- **Step 01** first (import regression test scaffold).

### Phase B (fully parallel import-path fixes)

Run in parallel after Step 01:

- Step 02
- Step 03
- Step 04
- Step 05
- Step 06
- Step 07
- Step 08

Reason: each step changes exactly one independent file in `project_management_mcp_commands`.

### Phase C (vectorization contract branch)

Run in parallel with Phase B after Step 01:

- Step 09
- Step 10

Constraint: Step 10 may run independently, but Step 09 must be rechecked after Step 10 merge.

### Phase D (FK-race hardening branch)

Run in parallel with Phases B/C after Step 01:

- Step 11
- Step 12

Constraint: Step 12 depends on behavior introduced in Step 11.

### Phase E (integration tests)

After all Phase B/C/D branches merged:

- Step 13

---

## Synchronization points

1. **Sync-1:** Step 01 complete before any parallel branch.
2. **Sync-2:** Steps 02-10 complete before Step 11 final verification.
3. **Sync-3:** Steps 11 and 12 complete before Step 13.
4. **Sync-4:** After Step 13, run full test suite.

---

## Blackstops

- If a step touches more than one code file: stop, split into new steps.
- If import fix introduces new unresolved imports: stop and report file + import path.
- If FK guard changes semantics of successful indexing for valid project: stop and report before merge.
- If full test suite is not green: task not complete.

