# Step 09 - Usages response contract

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** AST command developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/ast/usages.py`

## Goal

Include `file_path` and `cst_node_id` in `find_usages` response entities.

## Blackstops

- No response path without `cst_node_id`.
- No fallback identity by line/range.

## Success metric

- Usages response entity records include `file_path` + valid UUID4 `cst_node_id`.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run command and validate payload.
