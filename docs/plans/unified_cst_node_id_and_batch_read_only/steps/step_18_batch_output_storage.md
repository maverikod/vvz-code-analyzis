# Step 18 - Oversize output serialization and metadata module

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** Data serialization developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/read_only_batch_output.py`

## Goal

Isolate oversized batch output handling into dedicated module.

## Required behavior

- Serialize combined result deterministically.
- Compute per-command `size`, `offset`, `length`.
- Write oversized payload to output file.
- Return metadata structure used by batch command response.

## Blackstops

- No approximate offsets.
- No inline oversized payload fallback.
- No non-deterministic serialization for metadata calculations.

## Success metric

- Byte-range extraction using returned `offset/length` reproduces exact command fragments.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Validate with small and large synthetic payloads.
