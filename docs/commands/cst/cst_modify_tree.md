# cst_modify_tree

**Command name:** `cst_modify_tree`  
**Class:** `CSTModifyTreeCommand`  
**Source:** `code_analysis/commands/cst_modify_tree_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The cst_modify_tree command modifies a CST tree with atomic operations. All operations in a batch are validated before being applied. If any operation fails, all changes are rolled back and the tree remains unchanged.

Operation flow:
1. Validates tree_id exists
2. Validates all operations (checks node_ids, code syntax)
3. If all valid, applies all operations atomically
4. Validates modified module (compiles it)
5. Updates tree in memory
6. Returns success with operations_applied count

Supported Operations:
- replace: Replace a node with new code
  - Requires: node_id, code (or code_lines)
- insert: Insert a new node (or a comment-only line)
  - Requires: (parent_node_id OR target_node_id), code or code_lines, position: `first`, `last`, `after` (with `{"after": N}` for 0-based sibling index), or legacy `before`/`after`/`end`
  - parent_node_id: Use `__root__` for module-level placement. Position: first, last, or after N.
  - target_node_id: Insert before/after specific target node
  - Comment-only code is allowed (inserted as EmptyLine with Comment).
- move: Move an existing node to a new parent and/or position
  - Requires: node_id, parent_node_id (or `__root__`), position: `first`, `last`, or `after` with `{"after": N}`
- delete: Delete a node
  - Requires: node_id

Optional apply + save in one request:
- When both `project_id` and `file_path` are set, after applying operations the tree is saved to the file (same semantics as cst_save_tree). On save failure: file and database unchanged, in-memory tree is rolled back; response includes `save_error` and `save_error_cause`.

Atomicity:
- All operations are validated before any are applied
- If any operation fails validation, none are applied
- If module validation fails after applying operations, tree is rolled back
- Tree remains unchanged if any error occurs

Use cases:
- Batch modifications to code structure
- Refactoring operations
- Code transformations
- Multiple related changes in one operation

Important notes:
- **node_id** values are UUID4 (from cst_load_file / cst_find_node). They stay valid for unmodified nodes between operations in the same batch, so you can apply several replace/delete operations in one call.
- Operations are applied in order
- Use cst_save_tree to persist changes to file
- Tree modifications are in-memory until saved
- All operations must be valid for any to be applied

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tree_id` | string | **Yes** | Tree ID from cst_load_file |
| `operations` | array | **Yes** | List of operations to apply atomically |
| `preview` | boolean | No | Preview mode: show changes without applying (default: false) |
| `project_id` | string | No | When set with file_path: apply operations then save tree to file |
| `file_path` | string | No | Target file path (relative to project root); used with project_id for apply+save |
| `validate` | boolean | No | Validate before saving when project_id+file_path set (default: true) |
| `backup` | boolean | No | Create backup when saving (default: true) |
| `commit_message` | string | No | Optional git commit message when saving |

Operation object: `action` (replace | replace_range | insert | delete | move), `node_id`, `code` or `code_lines`, `parent_node_id` (use `__root__` for module level), `position` (`first` | `last` | `after` or `{"after": N}`), `target_node_id`, `start_node_id`/`end_node_id` (for replace_range).

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `tree_id`: Tree ID (same as input)
- `operations_applied`: Number of operations successfully applied

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** INVALID_OPERATION, CST_MODIFY_ERROR (and others).

---

## Examples

### Correct usage

**Replace a function**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "operations": [
    {
      "action": "replace",
      "node_id": "function:old_function:FunctionDef:10:0-20:0",
      "code": "def new_function():\n    return 'updated'"
    }
  ]
}
```

Replaces old_function with new_function. The code must be valid Python syntax. Operation is atomic - if code is invalid, tree remains unchanged.

**Delete a statement**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "operations": [
    {
      "action": "delete",
      "node_id": "smallstmt:Pass:15:4-15:8"
    }
  ]
}
```

Deletes a pass statement. Node must exist in tree. If node_id is invalid, operation fails and tree remains unchanged.

**Insert a comment line (e.g. mypy directive)**  
Insert accepts comment-only code. The parser normally returns no statement for a line like `# mypy: ignore-errors`; the command treats it as an `EmptyLine` with a `Comment` and inserts it.
```json
{
  "action": "insert",
  "parent_node_id": "<module_node_id>",
  "target_node_id": "<first_statement_node_id>",
  "code": "# mypy: ignore-errors",
  "position": "before"
}
```

**Insert statement before existing code**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "operations": [
    {
      "action": "insert",
      "parent_node_id": "function:process_data:FunctionDef:10:0-30:0",
      "code": "    logger.info('Starting processing')",
      "position": "before"
    }
  ]
}
```

Inserts a logging statement at the beginning of process_data function. Position 'before' means it will be inserted before existing function body. Parent node must exist and be a container (function, class, etc.).

**Insert statement after existing code**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "operations": [
    {
      "action": "insert",
      "parent_node_id": "function:process_data:FunctionDef:10:0-30:0",
      "code": "    logger.info('Processing complete')",
      "position": "after"
    }
  ]
}
```

Inserts a logging statement at the end of process_data function. Position 'after' means it will be inserted after existing function body.

**Batch operations - multiple replacements**
```json
{
  "tree_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "operations": [
    {
      "action": "replace",
      "node_id": "function:func1:FunctionDef:10:0-15:0",
      "code": "def func1():\n    return 'updated1'"
    },
    {
      "action": "replace",
      "node_id": "function:func2:FunctionDef:20:0-25:0",
      "code": "def func2():\n    return 'updated2'"
    }
  ]
}
```

Applies multiple replacements atomically. If any operation fails, all operations are rolled back. Useful for related changes that must succeed together.

### Incorrect usage

- **INVALID_OPERATION**: Invalid operation parameters. Check operation parameters:
- For replace: node_id must exist, code must be valid Python
- For delete: node_id must exist
- For insert: (parent_node_id OR target_node_id) must be provided, code must be valid Python, position must be 'before' or 'after'
All operations in a batch are validated before any are applied.

- **CST_MODIFY_ERROR**: Error during tree modification. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `INVALID_OPERATION` | Invalid operation parameters | Check operation parameters:
- For replace: node_id |
| `CST_MODIFY_ERROR` | Error during tree modification |  |

## Best practices

- Validate all operations before calling cst_modify_tree
- Use batch operations for related changes (atomicity)
- Test code syntax before using in replace/insert operations
- Use cst_load_file or query_cst to get valid node_ids
- Operations are applied in order - consider dependencies
- Use cst_save_tree to persist changes to file
- Tree modifications are in-memory until saved
- If any operation fails, all operations are rolled back

---
