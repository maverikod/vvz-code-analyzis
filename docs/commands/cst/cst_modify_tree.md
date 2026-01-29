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
  - Requires: node_id, code
- insert: Insert a new node
  - Requires: (parent_node_id OR target_node_id), code, position ('before' or 'after')
  - parent_node_id: Insert at beginning/end of parent's body
  - target_node_id: Insert before/after specific target node
- delete: Delete a node
  - Requires: node_id

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
- Operations are applied in order
- Use cst_save_tree to persist changes to file
- Tree modifications are in-memory until saved
- All operations must be valid for any to be applied

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tree_id` | string | **Yes** | Tree ID from cst_load_file |
| `preview` | boolean | No | Preview mode: show changes without applying (default: false) |
| `operations` | array | **Yes** | List of operations to apply atomically |

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
