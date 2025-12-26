# MCP Proxy Bug Report

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-26

## Problem Description

All MCP Proxy commands return error: `"MCP error -32602: Invalid request parameters"`

## Tested Commands and Formats

### 1. list_servers

**Attempt 1**: Without parameters
```python
mcp_MCP-Proxy-2_list_servers()
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

**Attempt 2**: With default parameters
```python
mcp_MCP-Proxy-2_list_servers(
    page=1,
    page_size=50
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

**Attempt 3**: With filter_enabled as boolean
```python
mcp_MCP-Proxy-2_list_servers(
    page=1,
    page_size=50,
    filter_enabled=True
)
```
**Result**: Error: `Parameter 'filter_enabled' must be one of types [boolean, null], got string`

**Attempt 4**: With filter_enabled as null
```python
mcp_MCP-Proxy-2_list_servers(
    page=1,
    page_size=50,
    filter_enabled=None
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

### 2. help

**Attempt 1**: Without parameters
```python
mcp_MCP-Proxy-2_help()
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

**Attempt 2**: With empty server_id
```python
mcp_MCP-Proxy-2_help(
    server_id="",
    command=""
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

**Attempt 3**: With server_id and command
```python
mcp_MCP-Proxy-2_help(
    server_id="code-analysis-server",
    command="help"
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

**Attempt 4**: With different server_ids
```python
mcp_MCP-Proxy-2_help(
    server_id="vectorization-server",
    command=""
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

### 3. call_server

**Attempt 1**: Call help on code-analysis-server
```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="help",
    params={}
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

**Attempt 2**: Call help with cmdname parameter
```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="help",
    params={"cmdname": "get_worker_status"}
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

**Attempt 3**: Call get_worker_status
```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="get_worker_status",
    params={"worker_type": "file_watcher"}
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

**Attempt 4**: Call with different server_ids
```python
mcp_MCP-Proxy-2_call_server(
    server_id="vectorization-server",
    command="help",
    params={}
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

### 4. health_check

**Attempt 1**: Without parameters
```python
mcp_MCP-Proxy-2_health_check()
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

**Attempt 2**: With check_type
```python
mcp_MCP-Proxy-2_health_check(
    check_type="basic"
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

### 5. echo

**Attempt 1**: With message
```python
mcp_MCP-Proxy-2_echo(
    message="test"
)
```
**Result**: `{"error":"MCP error -32602: Invalid request parameters"}`

## Expected Behavior

1. `list_servers` should return a list of registered servers
2. `help` should return help information for commands or servers
3. `call_server` should execute commands on registered servers
4. `health_check` should return server health status
5. `echo` should echo back the message

## Actual Behavior

All commands return the same error: `"MCP error -32602: Invalid request parameters"`

## Environment

- **OS**: Linux 6.8.0-90-generic
- **Python**: 3.12
- **MCP Proxy**: MCP-Proxy-2
- **Server**: code-analysis-server (running on port 15000)

## Server Status

The code-analysis-server is running and accessible:
- **Port**: 15000
- **Health endpoint**: `https://localhost:15000/health` returns OK
- **Registered commands**: 37 commands
- **Direct command execution**: Works correctly (tested via Python)

## Analysis

### Possible Causes

1. **MCP Proxy Configuration Issue**: The proxy may not be properly configured or connected
2. **Server Registration**: Servers may not be registered in MCP Proxy
3. **Parameter Format**: The parameter format expected by MCP Proxy may differ from what's being sent
4. **MCP Protocol Version**: There may be a version mismatch between the client and proxy
5. **Authentication**: The proxy may require authentication that's not being provided

### Observations

1. All commands fail with the same error code (-32602)
2. Error code -32602 is a JSON-RPC "Invalid params" error
3. The server itself works correctly when accessed directly
4. Commands are registered and work when called directly via Python

## Recommendations

1. **Check MCP Proxy Configuration**: Verify that MCP Proxy is properly configured and running
2. **Verify Server Registration**: Ensure that servers are registered in MCP Proxy
3. **Check Parameter Format**: Verify the expected parameter format for MCP Proxy commands
4. **Review MCP Proxy Logs**: Check logs for more detailed error information
5. **Test with Known Working Commands**: Try calling commands that are known to work
6. **Verify MCP Protocol Version**: Ensure client and proxy use compatible protocol versions

## Related Files

- MCP Proxy configuration (if exists)
- Server registration files
- MCP Proxy logs

## Correct Usage Format (From Guide)

According to the MCP Proxy usage guide, commands should be called with proper parameter types:

### Key Rules:
1. **Strings**: Use quoted strings like `"localhost"`, `"code-analysis-server"`
2. **Integers**: Use numbers like `1`, `20`, `15000`
3. **Booleans**: Use `true`/`false` (not strings `"true"`/`"false"`)
4. **Null values**: Use `null` for optional parameters (not empty strings `""`)
5. **Objects**: Use `{}` for empty objects, `{"key": "value"}` for objects with data

### Correct Examples:

```python
# list_servers - without parameters (uses defaults)
mcp_MCP-Proxy-2_list_servers()

# help - get general help
mcp_MCP-Proxy-2_help()

# call_server - with empty params object
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="help",
    params={}  # Empty object, not None
)

# call_server - with parameters
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="help",
    params={"cmdname": "get_worker_status"}
)
```

### Common Mistakes:
- ❌ Using empty strings `""` instead of `null` for optional parameters
- ❌ Missing `params={}` in `call_server` calls
- ❌ Using `"true"`/`"false"` strings instead of boolean `true`/`false`
- ❌ Using `None` instead of `{}` for empty params

## Updated Analysis

Despite following the correct format from the guide, all commands still return `-32602: Invalid request parameters`. This suggests:

1. **Tool Implementation Issue**: The MCP Proxy tools may not be correctly translating Python parameters to JSON-RPC format
2. **Configuration Issue**: MCP Proxy may not be properly configured or connected
3. **Server Registration**: Servers may not be registered in MCP Proxy
4. **Protocol Mismatch**: There may be a version or protocol mismatch

## Next Steps

1. Review MCP Proxy configuration
2. Check MCP Proxy logs for detailed error messages
3. Verify server registration in MCP Proxy
4. Test with a minimal working example using the correct format
5. Verify tool implementation correctly translates parameters to JSON-RPC
6. Contact MCP Proxy maintainers if issue persists

