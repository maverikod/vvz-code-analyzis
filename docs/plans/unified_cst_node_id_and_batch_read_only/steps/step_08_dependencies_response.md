# Step 08 - Dependencies response contract

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** AST command developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/ast/dependencies.py`

## Goal

Include `file_path` and `cst_node_id` in `find_dependencies` response entities.

## Blackstops

- No line-only entity identity in final payload.
- No invalid/empty `cst_node_id`.

## Success metric

- Dependencies response includes `file_path` and valid UUID4 IDs for entity nodes.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run command and validate response schema.
