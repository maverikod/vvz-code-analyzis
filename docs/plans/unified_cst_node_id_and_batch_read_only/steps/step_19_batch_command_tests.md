# Step 19 - Batch command test coverage

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** Test developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`tests/test_read_only_batch_command.py`

## Goal

Provide explicit coverage for batch read-only contract and oversized output path.

## Required test cases

- Accept whitelisted read-only commands.
- Reject non-whitelisted/mutating commands.
- Inline response when payload is below threshold.
- File output response when payload exceeds threshold.
- Validate `file_size` and per-command `size/offset/length` consistency.

## Blackstops

- No skipped critical cases.
- No tests that assert fallback behavior banned by TZ.

## Success metric

- Tests fail on contract violations and pass on correct implementation.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run `pytest tests/test_read_only_batch_command.py`.
