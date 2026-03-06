# Step 07 - Entity info response contract

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** AST command developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/ast/entity_info.py`

## Goal

Include `file_path` and `cst_node_id` in `get_code_entity_info` response.

## Blackstops

- No placeholder or backward-compat fallback behavior.
- No invalid UUID4 values.

## Success metric

- Returned entity info contains `file_path` and valid UUID4 `cst_node_id`.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run command and validate contract.
