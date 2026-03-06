# Step 14 - Implement batch read-only command

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** Command orchestration developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/read_only_batch_command.py`

## Goal

Implement orchestration for batch execution using dedicated whitelist/output modules.

## Required behavior

- Accept list of command invocations and orchestrate execution flow.
- Delegate whitelist checks to `read_only_batch_whitelist.py` (Step 17).
- Delegate oversized output serialization/file metadata to `read_only_batch_output.py` (Step 18).
- Build final response envelope for both inline and file-metadata modes.

## Blackstops

- No dynamic whitelist extension from client/config.
- No oversized inline payload when threshold is exceeded.
- Do not duplicate whitelist/storage logic in this file.

## Success metric

- Command orchestration is deterministic and integrates cleanly with Steps 17/18 contracts.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run small and oversized batch scenarios.
