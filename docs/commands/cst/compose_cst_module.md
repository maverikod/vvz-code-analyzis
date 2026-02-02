# compose_cst_module

**Command name:** `compose_cst_module`  
**Class:** `ComposeCSTModuleCommand`  
**Source:** `code_analysis/commands/cst_compose_module_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

Compose or overwrite a Python module using a CST tree (branch from `cst_load_file`). Either overwrites the target file with the branch code or inserts the branch after a given node. Before writing, the composed source is validated (compile, docstrings, flake8, mypy). The server normalizes the source to end with exactly one newline (PEP 8 / flake8 W391) before validation. If validation fails, the file is not written and a `VALIDATION_ERROR` is returned.

**Note:** This command can take 30+ seconds (mypy and DB operations). Ensure the MCP proxy or client timeout is at least 40–60 seconds for this command; otherwise the client may report the server as unavailable while the command is still running.

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project ID (UUID4). Required. |
| `file_path` | string | **Yes** | Target python file path (relative to project root) |
| `tree_id` | string | **Yes** | CST tree ID from cst_load_file command (branch to attach) |
| `node_id` | string | No | Node ID to attach branch to (optional). If empty - file will be overwritten with branch. If specified - branch will be inserted after the node. |
| `commit_message` | string | No | Optional git commit message |

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
