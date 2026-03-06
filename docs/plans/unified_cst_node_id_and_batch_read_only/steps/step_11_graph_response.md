# Step 11 - Graph export entity contract

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** AST graph command developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/ast/graph.py`

## Goal

Ensure graph export nodes representing entities include `file_path` and `cst_node_id`.

## Blackstops

- Do not break existing graph topology fields.
- Do not output entity graph nodes without valid IDs.

## Success metric

- Entity graph nodes include `file_path` + valid UUID4 `cst_node_id`.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run graph export and validate node payload.
