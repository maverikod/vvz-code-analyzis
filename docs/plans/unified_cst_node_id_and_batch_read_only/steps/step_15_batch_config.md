# Step 15 - Add batch output configuration

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** Configuration developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/core/config.py`

## Goal

Add and validate config keys for batch output threshold and output file policy.

## Required keys

- `batch_max_response_bytes`
- `batch_output_dir`
- `batch_output_retention_seconds` (or equivalent retention key)

## Blackstops

- No hidden defaults that bypass overflow-to-file contract.
- No writable path outside project policy.

## Success metric

- Config loads/validates keys and batch command consumes them.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Validate config with valid/invalid values.
