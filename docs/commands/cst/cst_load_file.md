# cst_load_file

**Command name:** `cst_load_file`  
**Class:** `CSTLoadFileCommand`  
**Source:** `code_analysis/commands/cst_load_file_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The cst_load_file command loads a Python file into a CST tree and stores it in memory. It returns a tree_id that can be used with other CST tree commands (cst_modify_tree, cst_save_tree, cst_find_node). The full CST tree is stored on the server, and only node metadata is returned to the client.

Operation flow:
1. Gets project from database using project_id
2. Validates project is linked to watch directory
3. Gets watch directory path from database
4. Forms absolute path: watch_dir_path / project_name / file_path
5. Validates file is a .py file
6. Validates file exists
7. Reads file source code
8. Parses source using LibCST
9. Builds node index and metadata
10. Stores tree in memory with tree_id
11. Returns tree_id and node metadata

Node Metadata:
Each node includes:
- node_id: Stable identifier for operations
- type: LibCST node type (FunctionDef, ClassDef, etc.)
- kind: Node kind (function, class, method, stmt, smallstmt, etc.)
- name: Node name (if applicable)
- qualname: Qualified name (if applicable)
- start_line, start_col, end_line, end_col: Position
- children_count: Number of children
- children_ids: List of child node IDs (if include_children=True)
- parent_id: Parent node ID (if applicable)

Filters:
- node_types: Filter by node types (e.g., ['FunctionDef', 'ClassDef'])
- max_depth: Limit depth of nodes returned
- include_children: Whether to include children information

Use cases:
- Load file for modification operations
- Analyze code structure
- Find specific nodes for refactoring
- Prepare for batch operations

Important notes:
- Tree is stored in memory on the server
- Tree persists until explicitly removed or server restarts
- Use tree_id with other CST commands
- Filters reduce returned metadata, but full tree is still stored

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project ID (UUID4). Required. |
| `file_path` | string | **Yes** | Target Python file path (relative to project root) |
| `node_types` | array | No | Optional filter by node types (e.g., ['FunctionDef', 'ClassDef']) |
| `max_depth` | integer | No | Optional maximum depth for node filtering |
| `include_children` | boolean | No | Whether to include children information in metadata Default: `true`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `tree_id`: Tree ID for use with other CST commands
- `file_path`: Path to loaded file
- `nodes`: List of node metadata dictionaries
- `total_nodes`: Total number of nodes returned

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** FILE_NOT_FOUND, INVALID_FILE, CST_LOAD_ERROR (and others).

---

## Examples

### Correct usage

**Load file without filters**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/main.py"
}
```

Loads entire file into CST tree. Returns all nodes with full metadata. Absolute path is formed as: watch_dir_path / project_name / src/main.py. Use this when you need to work with all nodes in the file.

**Load only functions and classes**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/models.py",
  "node_types": [
    "FunctionDef",
    "ClassDef"
  ]
}
```

Loads file but returns metadata only for functions and classes. Useful when you only need to work with top-level definitions. Full tree is still stored, but metadata is filtered.

**Load with depth limit**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/main.py",
  "max_depth": 2
}
```

Loads file but returns nodes only up to depth 2. Useful for analyzing top-level structure without deep nesting details.

**Load without children information**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/utils.py",
  "include_children": false
}
```

Loads file but excludes children_ids from metadata. Reduces response size when children information is not needed.

**Load specific statement types**
```json
{
  "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
  "file_path": "src/main.py",
  "node_types": [
    "If",
    "For",
    "Try",
    "With"
  ]
}
```

Loads file but returns only control flow statements (if, for, try, with). Useful for analyzing control flow patterns.

### Incorrect usage

- **FILE_NOT_FOUND**: File does not exist. Verify file_path is correct and file exists

- **INVALID_FILE**: File is not a Python file. Ensure file_path points to a .py file

- **CST_LOAD_ERROR**: Error during file loading. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `FILE_NOT_FOUND` | File does not exist | Verify file_path is correct and file exists |
| `INVALID_FILE` | File is not a Python file | Ensure file_path points to a .py file |
| `CST_LOAD_ERROR` | Error during file loading |  |

## Best practices

- Always provide project_id - it is required and used to form absolute path
- Ensure project is linked to watch directory before using this command
- Use relative file_path from project root (e.g., 'src/main.py' not '/absolute/path')
- Use node_types filter to reduce metadata size when only specific types are needed
- Use max_depth to limit analysis scope
- Set include_children=False if children information is not needed
- Save tree_id for use with cst_modify_tree and cst_save_tree
- Tree persists in memory until server restart or explicit removal

---
