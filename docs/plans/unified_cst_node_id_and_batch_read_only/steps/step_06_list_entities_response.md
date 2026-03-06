# Step 06 - List entities response contract

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** AST command developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/ast/list_entities.py`

## Goal

Return `file_path` and `cst_node_id` for each entity in `list_code_entities`.

## Blackstops

- No fallback to line-only identity.
- No empty `cst_node_id`.

## Success metric

- All returned entities include `file_path` + valid UUID4 `cst_node_id`.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run command and validate payload.
