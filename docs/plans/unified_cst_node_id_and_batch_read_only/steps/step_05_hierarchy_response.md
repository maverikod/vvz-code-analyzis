# Step 05 - Hierarchy response contract

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** AST command developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/ast/hierarchy.py`

## Goal

Ensure hierarchy entities include `file_path` and valid `cst_node_id`.

## Blackstops

- Do not remove existing response fields.
- Do not return empty or invalid `cst_node_id`.

## Success metric

- `get_class_hierarchy` response includes `file_path` + `cst_node_id` for entity nodes.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run command and validate response contract.
