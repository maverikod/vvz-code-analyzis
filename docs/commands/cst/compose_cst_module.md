# compose_cst_module

**Command name:** `compose_cst_module`  
**Class:** `ComposeCSTModuleCommand`  
**Source:** `code_analysis/commands/cst_compose_module_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

No description in schema.

---

## Arguments (Аргументы)

Either **tree_id** (branch attach) or **ops** (selector-based patches) must be provided.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project ID (UUID4). Required. |
| `file_path` | string | **Yes** | Target python file path (relative to project root) |
| `tree_id` | string | No* | CST tree ID from cst_load_file (branch to attach). Use with `node_id` for insert. *Required if `ops` not provided. |
| `node_id` | string | No | Node ID to attach branch to (tree_id mode only). If empty - overwrite file with branch. |
| `ops` | array | No* | List of replace operations. Each item: `{ "selector": { "kind", ... }, "new_code" [, "file_docstring" ] }`. *Required if `tree_id` not provided. |
| `apply` | boolean | No | If true (default), write result to file. If false, only return diff/stats (ops mode). |
| `create_backup` | boolean | No | If true (default), create file backup before writing (ops mode, when apply=true). |
| `return_diff` | boolean | No | If true, include unified diff in response (ops mode). When apply=false, returns diff without writing. |
| `commit_message` | string | No | Optional git commit message |

**Selector kinds** (for `ops[].selector.kind`): `module`, `function`, `class`, `method`, `range`, `block_id`, `node_id`, `cst_query`.

- **range**: `start_line`, `end_line` (required); optional `start_col`, `end_col`.
- **block_id**: `block_id` (from `list_cst_blocks`).
- **node_id**: `node_id` (from `query_cst`).
- **cst_query**: `query` (required); optional `match_index` (non-negative).
- **function** / **class** / **method**: `name` (required).
- **module**: create module from scratch; op must include `file_docstring` and `new_code`.

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.

### Error

- **Shape:** `ErrorResult` with `code` and `message`.

---

## Examples

### Correct usage

Use required parameters from the Arguments table above.

### Incorrect usage

- Missing required parameters → schema validation error or command-specific error (e.g. PROJECT_NOT_FOUND).

---
