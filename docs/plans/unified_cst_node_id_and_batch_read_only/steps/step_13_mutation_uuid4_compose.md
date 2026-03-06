# Step 13 - UUID4-only mutation target in compose_cst_module

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** CST compose command developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/cst_compose_module_command.py`

## Goal

Align compose mutation flow with immutable UUID4 target contract.

## Required behavior

- Validate `node_id` as UUID4 in mutation path.
- Reject invalid target IDs before write.
- Keep compatibility selectors only if they resolve to UUID4 before mutation.

## Blackstops

- No primary line/range mutation path.
- No fallback write behavior on invalid ID.

## Success metric

- Compose operations mutate only resolved UUID4 targets and fail fast otherwise.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run compose scenarios and UUID4 validation checks.
