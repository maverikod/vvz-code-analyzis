# Step 10 - Entity dependencies/dependents response contract

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** AST command developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/ast/entity_dependencies.py`

## Goal

Include `file_path` and `cst_node_id` in `get_entity_dependencies` and `get_entity_dependents` responses.

## Blackstops

- Do not leave mixed formats where only part of entities carry IDs.
- Do not emit invalid UUID4 values.

## Success metric

- Both dependency directions return entities with `file_path` + valid `cst_node_id`.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Run both commands and validate response contract.
