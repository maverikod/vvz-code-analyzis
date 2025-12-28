# MCP Proxy - Correct Command Usage Guide

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-26

## Overview

This guide explains how to correctly call MCP Proxy commands with parameters. All commands are working correctly when called with proper parameter format.

## General Rules

### 1. Parameter Types

- **Strings**: Use quoted strings like `"localhost"`, `"code-analysis-server"`
- **Integers**: Use numbers like `1`, `20`, `15000`
- **Booleans**: Use `true`/`false` (not strings `"true"`/`"false"`)
- **Null values**: Use `null` for optional parameters (not empty strings `""`)
- **Objects**: Use `{}` for empty objects, `{"key": "value"}` for objects with data

### 2. Optional Parameters

- If a parameter is optional and you don't want to provide it, **omit it entirely** or use `null`
- **DO NOT** use empty strings `""` for optional parameters
- Empty strings are treated as actual string values, not as "no value"

## Command Examples

### 1. `list_servers`

**Correct Usage:**

```python
# Without parameters (uses defaults)
mcp_MCP-Proxy-2_list_servers()

# With explicit parameters
mcp_MCP-Proxy-2_list_servers(
    page=1,
    page_size=20
)

# With filter_enabled as boolean
mcp_MCP-Proxy-2_list_servers(
    page=1,
    page_size=20,
    filter_enabled=True  # or False
)

# With filter_enabled as null (no filter)
mcp_MCP-Proxy-2_list_servers(
    page=1,
    page_size=20,
    filter_enabled=None
)
```

**Incorrect Usage:**

```python
# ❌ WRONG: Empty string for optional parameter
mcp_MCP-Proxy-2_list_servers(
    filter_enabled=""  # This is treated as a string, not null!
)
```

### 2. `help`

**Correct Usage:**

```python
# Get general help (no parameters needed)
mcp_MCP-Proxy-2_help()

# Get help for specific server
mcp_MCP-Proxy-2_help(
    server_id="code-analysis-server",
    command=""  # Empty string is OK here if you want server help
)

# Get help for specific command on server
mcp_MCP-Proxy-2_help(
    server_id="code-analysis-server",
    command="get_worker_status"
)
```

**Incorrect Usage:**

```python
# ❌ WRONG: Missing required parameters when you want specific help
mcp_MCP-Proxy-2_help(
    server_id=""  # Empty string might not work as expected
)
```

### 3. `call_server`

**Correct Usage:**

```python
# IMPORTANT:
# - Use server_id + copy_number (not server_key)
# - Always pass params as an object ({} if no params)
# - For code-analysis-server you usually want:
#   server_id="code-analysis-server", copy_number=1
#
# Call command without parameters
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="help",
    params={}  # Empty object for no parameters
)

# Call command with parameters
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="get_worker_status",
    params={
        "worker_type": "file_watcher"
    }
)

# Call command with multiple parameters
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="help",
    params={
        "cmdname": "get_worker_status"
    }
)
```

### 3.1 Long-running commands (queue)

Some server commands are configured as `use_queue=True` (example: `update_indexes`). They return a `job_id`.

Use queue commands on the SAME server to track them:

```python
# Start update_indexes (queued)
res = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="update_indexes",
    params={"root_dir": "/abs/path"}
)

# Track status and logs
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="queue_get_job_status",
    params={"job_id": res["result"]["job_id"]}
)
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="queue_get_job_logs",
    params={"job_id": res["result"]["job_id"]}
)
```

**Incorrect Usage:**

```python
# ❌ WRONG: Missing params parameter
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="help"
    # params is required!
)

# ❌ WRONG: Using None instead of empty object
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="help",
    params=None  # Should be {} for no parameters
)
```

### 4. `health_check`

**Correct Usage:**

```python
# Without parameters (uses default "basic")
mcp_MCP-Proxy-2_health_check()

# With explicit check_type
mcp_MCP-Proxy-2_health_check(
    check_type="basic"
)
```

### 5. `echo`

**Correct Usage:**

```python
mcp_MCP-Proxy-2_echo(
    message="test"
)
```

## Common Mistakes

### Mistake 1: Using Empty Strings Instead of Null

**Wrong:**
```python
mcp_MCP-Proxy-2_list_servers(
    filter_enabled=""  # Empty string is NOT the same as null
)
```

**Correct:**
```python
mcp_MCP-Proxy-2_list_servers(
    filter_enabled=None  # Use null for optional parameters
)
# OR simply omit it:
mcp_MCP-Proxy-2_list_servers()
```

### Mistake 2: Missing Required Parameters

**Wrong:**
```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="help"
    # Missing params!
)
```

**Correct:**
```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="help",
    params={}  # Always provide params, even if empty
)
```

### Mistake 3: Wrong Parameter Types

**Wrong:**
```python
mcp_MCP-Proxy-2_list_servers(
    filter_enabled="true"  # String, not boolean!
)
```

**Correct:**
```python
mcp_MCP-Proxy-2_list_servers(
    filter_enabled=True  # Boolean value
)
```

### Mistake 4: Incorrect Object Format

**Wrong:**
```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="get_worker_status",
    params="worker_type=file_watcher"  # String, not object!
)
```

**Correct:**
```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="get_worker_status",
    params={
        "worker_type": "file_watcher"  # Proper object/dict
    }
)
```

## Parameter Validation

The MCP Proxy validates parameters according to JSON Schema. Common validation errors:

1. **Type Mismatch**: Parameter must be of specific type (string, integer, boolean, object, null)
2. **Required Parameter Missing**: All required parameters must be provided
3. **Invalid Enum Value**: Parameter value must be one of the allowed enum values
4. **Invalid Format**: String parameters must match required format (e.g., URL, UUID)

## Testing Your Calls

Before reporting errors, verify:

1. ✅ All required parameters are provided
2. ✅ Parameter types match the schema (string, int, bool, object, null)
3. ✅ Optional parameters use `null` or are omitted, not empty strings
4. ✅ Object parameters are proper dictionaries/objects, not strings
5. ✅ Boolean parameters use `true`/`false`, not `"true"`/`"false"`
6. ✅ Server ID exists in the registered servers list

## Getting Help

If you're unsure about parameter format:

1. Use `list_servers()` to see available servers and their commands
2. Use `help(server_id="your-server", command="your-command")` to get command schema
3. Check the command's `parameters` field in the server listing for the exact schema

## Example: Complete Workflow

```python
# Step 1: List available servers
servers = mcp_MCP-Proxy-2_list_servers()
print(f"Found {len(servers['servers'])} servers")

# Step 2: Get help for a specific server
help_info = mcp_MCP-Proxy-2_help(
    server_id="code-analysis-server",
    command=""
)

# Step 3: Get help for a specific command
command_help = mcp_MCP-Proxy-2_help(
    server_id="code-analysis-server",
    command="get_worker_status"
)

# Step 4: Call the command with correct parameters
result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="get_worker_status",
    params={
        "worker_type": "file_watcher"
    }
)
```

## Summary

**Key Points:**
- ✅ Use proper types: strings, integers, booleans, objects, null
- ✅ Always provide `params={}` for `call_server`, even if empty
- ✅ Use `null` or omit optional parameters, not empty strings
- ✅ Use `true`/`false` for booleans, not `"true"`/`"false"`
- ✅ Use dictionaries/objects for `params`, not strings
- ✅ Check server and command existence before calling

**Remember:** The error "MCP error -32602: Invalid request parameters" means your parameter format is incorrect. Review the command schema and ensure all parameters match the expected types and formats.

