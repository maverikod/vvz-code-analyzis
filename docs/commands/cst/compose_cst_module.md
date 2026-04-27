# compose_cst_module

**Command name:** `compose_cst_module`  
**Class:** `ComposeCSTModuleCommand`  
**Source:** `code_analysis/commands/cst_compose_module_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The compose_cst_module command applies CST changes to a file with atomic operations. Two modes: (1) tree_id + optional node_id — attach a branch (CST tree) to a node or overwrite file; (2) ops — list of selector + new_code patches (e.g. replace by function name, range, cst_query). Selector kinds: module, function, class, method, range, block_id, node_id, cst_query. For **range** without columns, the patcher replaces the statement that matches the line span and **preserves blank lines above** that statement (LibCST `leading_lines` on the same node — important for single-line imports and spacing before classes). When apply=true (default), validates (compile, flake8, mypy, docstrings), backs up, and writes. Use apply=false with return_diff=true to preview without writing.

Important for AI usage:
- compose_cst_module (apply=true) performs full quality validation before write.
- If your task is narrow (for example only adding docstrings) and full validation blocks write,
  use cst_modify_tree + cst_save_tree workflow, then run quality checks explicitly.
- Always start with apply=false, return_diff=true before applying.

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project ID (UUID4). Required. |
| `file_path` | string | **Yes** | Target python file path (relative to project root) |
| `tree_id` | string | No | CST tree ID from cst_load_file (branch to attach). Use either tree_id or ops, not both. |
| `node_id` | string | No | Node ID to attach branch to (tree_id mode only). If empty - overwrite file with branch. |
| `ops` | array | No | List of replace operations (ops mode). Each item: { selector: { kind, ... }, new_code [, file_docstring ] }. Selector kinds: module, function, class, method, range, block_id, node_id, cst_query. See **Selector `range`** below. |
| `apply` | boolean | No | If true (default), write result to file. If false, only compute and return diff/stats (ops mode). Default: `true`. |
| `create_backup` | boolean | No | If true (default), create file backup before writing (ops mode, when apply=true). Default: `true`. |
| `return_diff` | boolean | No | If true, include unified diff in response (ops mode). When apply=false, returns diff without writing. Default: `false`. |
| `commit_message` | string | No | Optional git commit message |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

### Selector range

Семантика селектора `kind: "range"`:

- **Без `start_col` / `end_col`:** заменяется **одно** верхнеуровневое утверждение модуля (statement), у которого в LibCST позиция **ровно** совпадает с парой `(start_line, end_line)` — номера строк **1-based**, концы включительно.
- **Пустые строки над** этим statement сохраняются: в LibCST они хранятся как `leading_lines` у этого же узла, а не как отдельные «строки файла» в диапазоне замены. Раньше при подстановке распарсенного `new_code` эти строки терялись; сейчас они переносятся на первую заменяющую конструкцию.
- **С `start_col` и `end_col`:** совпадение по точному символьному span (как у разрешённого из `node_id` range); сохранение `leading_lines` у исходного statement по-прежнему применяется при замене целого statement по span.
- **Замечание:** пустая строка **под** заменённым блоком обычно принадлежит **следующему** statement (`leading_lines` следующего узла) и не затрагивается заменой одной строки импорта.

Implementation: `code_analysis/core/cst_module/patcher.py` (`apply_replace_ops`, trivia при замене statement).

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

**Replace an import (ops mode, cst_query selector)**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "src/main.py",
  "ops": [
    {
      "selector": {
        "kind": "cst_query",
        "query": "ImportFrom[module='.task_status']",
        "match_index": 0
      },
      "new_code": "from ..task_status import TaskStatus"
    }
  ],
  "apply": true,
  "create_backup": true
}
```

Replaces the first ImportFrom matching the CSTQuery. Selector kinds for ops: module, function, class, method, range, block_id, node_id, cst_query.

**Replace code by line range (ops mode, range selector)**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "src/utils.py",
  "ops": [
    {
      "selector": {
        "kind": "range",
        "start_line": 10,
        "end_line": 15
      },
      "new_code": "# replaced lines 10-15"
    }
  ],
  "apply": false,
  "return_diff": true
}
```

Replaces the statement whose line span equals 10–15 (1-based). Blank lines immediately above that statement are preserved. `apply=false` returns diff without writing; use `apply=true` to write.

**Preview-only first, then apply**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "src/main.py",
  "ops": [
    {
      "selector": {
        "kind": "function",
        "name": "process_data"
      },
      "new_code": "def process_data(items):\n    \"\"\"Process input items and return normalized result.\"\"\"\n    return items"
    }
  ],
  "apply": false,
  "return_diff": true
}
```

Recommended pattern for AI: first preview changes with apply=false. If diff is correct, repeat with apply=true.

**Replace function by name (ops mode, function selector)**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "src/main.py",
  "ops": [
    {
      "selector": {
        "kind": "function",
        "name": "old_helper"
      },
      "new_code": "def old_helper():\n    return default"
    }
  ]
}
```

Replaces the function named old_helper with new code. Selector kind 'function' requires 'name'.

**Attach branch to node (tree_id mode)**
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "src/main.py",
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "node_id": "function:process_data:FunctionDef:10:0-30:0"
}
```

Inserts the CST tree (branch) from cst_load_file into the process_data function. Omit node_id to overwrite the entire file with the branch.

### Incorrect usage

- Missing required parameters → schema validation error or command-specific error (e.g. PROJECT_NOT_FOUND).

---
