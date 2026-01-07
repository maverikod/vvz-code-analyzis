# CST Editing Prompt for AI Models

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Purpose

This document provides a clear prompt/instruction set for AI models to ensure they **ALWAYS** use CST (Concrete Syntax Tree) tools when editing existing Python code, instead of direct file editing.

## Critical Rule

**🚨 FOR EXISTING PYTHON CODE: ALWAYS USE CST TOOLS FIRST 🚨**

When you need to modify existing `.py` files, you **MUST**:
1. Use `list_cst_blocks` to discover code structure
2. Use `compose_cst_module` (via MCP) to make changes
3. **NEVER** use `search_replace` or direct file editing for existing Python code

## Workflow Template

### Step 1: Discover Code Structure

```python
# Always start by listing blocks
blocks = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="list_cst_blocks",
    params={
        "root_dir": "/absolute/path/to/project",
        "file_path": "path/to/file.py"  # relative to root_dir
    }
)
```

**Output**: List of blocks with stable IDs:
```json
{
  "blocks": [
    {
      "id": "function:my_function:10-25",
      "kind": "function",
      "qualname": "my_function",
      "start_line": 10,
      "end_line": 25
    },
    {
      "id": "class:MyClass:30-100",
      "kind": "class",
      "qualname": "MyClass",
      "start_line": 30,
      "end_line": 100
    }
  ]
}
```

### Step 2: Query for Specific Nodes (Optional)

If you need to find specific nodes (e.g., return statements, imports):

```python
# Use CSTQuery selectors
matches = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="query_cst",
    params={
        "root_dir": "/absolute/path/to/project",
        "file_path": "path/to/file.py",
        "selector": "function[name='my_function'] smallstmt[type='Return']",
        "include_code": True,
        "max_results": 10
    }
)
```

**CSTQuery Examples**:
- `function[name="my_func"]` - Find function by name
- `class[name="MyClass"]` - Find class by name
- `method[qualname="MyClass.my_method"]` - Find method by qualified name
- `smallstmt[type="Return"]` - Find all return statements
- `function[name="f"] smallstmt[type="Return"]:first` - First return in function `f`

### Step 3: Preview Changes (Recommended)

```python
# Preview before applying
preview = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/absolute/path/to/project",
        "file_path": "path/to/file.py",
        "ops": [{
            "operation_type": "replace",  # or "insert", "create"
            "selector": {
                "kind": "block_id",  # or "function", "class", "method", "node_id", "cst_query", "range"
                "block_id": "function:my_function:10-25"
            },
            "new_code": "def my_function(param: int) -> str:\n    \"\"\"Updated function.\"\"\"\n    return str(param)"
        }],
        "apply": False,  # Preview only
        "return_diff": True,
        "return_source": False
        # commit_message not needed for preview
    }
)
```

**Check the diff** in `preview["data"]["diff"]` before applying.

### Step 4: Apply Changes

```python
# Apply with backup
result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/absolute/path/to/project",
        "file_path": "path/to/file.py",
        "ops": [{
            "operation_type": "replace",
            "selector": {
                "kind": "block_id",
                "block_id": "function:my_function:10-25"
            },
            "new_code": "def my_function(param: int) -> str:\n    \"\"\"Updated function.\"\"\"\n    return str(param)"
        }],
        "apply": True,  # Apply changes
        "create_backup": True,  # Create backup
        "return_diff": True,
        "return_source": False,
        "commit_message": "Refactor: update my_function"  # Required if git repository
    }
)
```

### Step 5: Validate

```python
# Format code
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="format_code",
    params={"file_path": "path/to/file.py"}
)

# Lint code
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="lint_code",
    params={"file_path": "path/to/file.py"}
)

# Type check
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="type_check_code",
    params={"file_path": "path/to/file.py"}
)
```

## Selector Types

### 1. Block ID (Recommended)

Use stable ID from `list_cst_blocks`:

```python
{
    "kind": "block_id",
    "block_id": "function:my_function:10-25"
}
```

### 2. Function/Class/Method Name

```python
# Function
{
    "kind": "function",
    "name": "my_function"
}

# Class
{
    "kind": "class",
    "name": "MyClass"
}

# Method (use qualified name)
{
    "kind": "method",
    "name": "MyClass.my_method"
}
```

### 3. Node ID (from query_cst)

```python
{
    "kind": "node_id",
    "node_id": "function:my_function:FunctionDef:10:0-25:10"
}
```

### 4. CSTQuery Selector

```python
{
    "kind": "cst_query",
    "query": "function[name='my_function']",
    "match_index": 0  # Optional: if multiple matches
}
```

### 5. Line Range

```python
{
    "kind": "range",
    "start_line": 10,
    "end_line": 25
}
```

## Operation Types

### Replace (Default)

Replace existing code block:

```python
{
    "operation_type": "replace",
    "selector": {...},
    "new_code": "new code here"
}
```

### Insert

Insert code before/after a block:

```python
{
    "operation_type": "insert",
    "selector": {...},
    "new_code": "new code here",
    "position": "before"  # or "after"
}
```

### Create

Create new code at end of file:

```python
{
    "operation_type": "create",
    "selector": null,  # No selector for create
    "new_code": "new code here"
}
```

### Delete

Remove code block (empty `new_code`):

```python
{
    "operation_type": "replace",
    "selector": {...},
    "new_code": ""  # Empty string = delete
}
```

## Common Patterns

### Pattern 1: Replace a Function

```python
# 1. List blocks
blocks = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="list_cst_blocks",
    params={"root_dir": "/path", "file_path": "file.py"}
)

# 2. Find function block_id
func_block = next(b for b in blocks["data"]["blocks"] if b["qualname"] == "my_function")

# 3. Replace
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "ops": [{
            "selector": {"kind": "block_id", "block_id": func_block["id"]},
            "new_code": "def my_function(param: int) -> str:\n    \"\"\"New implementation.\"\"\"\n    return str(param)"
        }],
        "apply": True,
        "create_backup": True
    }
)
```

### Pattern 2: Remove a Function

```python
# Same as Pattern 1, but with empty new_code
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "ops": [{
            "selector": {"kind": "function", "name": "unused_function"},
            "new_code": ""  # Delete
        }],
        "apply": True
    }
)
```

### Pattern 3: Replace a Method

```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "ops": [{
            "selector": {"kind": "method", "name": "MyClass.my_method"},
            "new_code": "def my_method(self, param: int) -> str:\n    \"\"\"Updated method.\"\"\"\n    return str(param)"
        }],
        "apply": True
    }
)
```

### Pattern 4: Add New Function

```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "ops": [{
            "operation_type": "create",
            "selector": null,
            "new_code": "def new_function(param: int) -> str:\n    \"\"\"New function.\"\"\"\n    return str(param)"
        }],
        "apply": True
    }
)
```

## When NOT to Use CST

**Use direct editing (`write`, `search_replace`) ONLY for**:
- ✅ Creating new files (file doesn't exist)
- ✅ Editing non-Python files (.md, .json, .yaml, etc.)
- ✅ Simple text replacements in comments (though CST is still preferred)

## Error Handling

If `compose_cst_module` fails:
1. Check the error message
2. Verify the selector is correct
3. Try a different selector type (e.g., `block_id` instead of `function`)
4. Use `query_cst` to verify the node exists
5. Only as a last resort, use `search_replace` (and document why CST failed)

## Benefits of Using CST

✅ **Preserves formatting** - Comments and whitespace are maintained  
✅ **Automatic validation** - Syntax, docstrings, type hints are checked  
✅ **Import normalization** - Imports are automatically organized  
✅ **Backup support** - Automatic backups before changes  
✅ **Diff preview** - See changes before applying  
✅ **Stable selectors** - Block IDs remain stable across edits  

## Remember

**🚨 ALWAYS use CST tools for existing Python code. Direct editing is ONLY for new files or when CST is not applicable. 🚨**

