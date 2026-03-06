# Step 17 - Hardcoded whitelist module

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** Command security developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/read_only_batch_whitelist.py`

## Goal

Extract hardcoded read-only whitelist and validation helper into dedicated module.

## Required behavior

- Define immutable whitelist constants.
- Provide helper API to validate a command name against whitelist.
- Produce explicit error payload for non-whitelisted command.

## Blackstops

- No dynamic expansion from user input or config.
- No mutating commands in whitelist.

## Success metric

- Batch command can import whitelist helper and reject non-whitelisted commands deterministically.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Negative test for mutating command rejection.
