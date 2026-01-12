# Bug Report: compose_cst_module range selector replacement error

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-01-12  
**Component**: code-analysis-server  
**Command**: `compose_cst_module`

## Summary

The `compose_cst_module` command fails with `ParserSyntaxError` when attempting to replace code using `range` selector. The error occurs during CST parsing of the replacement code.

## Error Details

### Error Message
```
CST_COMPOSE_ERROR: Syntax Error @ 3:9.
parser error: error at 2:8: expected one of (, *, +, -, ..., AWAIT, EOF, False, NAME, NUMBER, None, True, [, break, continue, lambda, match, not, pass, ~

        config.load()
        ^
```

### Command That Triggers the Error
```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="compose_cst_module",
    params={
        "root_dir": "/path/to/project",
        "file_path": "server.py",
        "ops": [{
            "operation_type": "replace",
            "selector": {
                "kind": "range",
                "start_line": 101,
                "end_line": 106
            },
            "new_code": "        # Load configuration\n        config = SimpleConfig(config_path)\n        config.load()\n        \n        # Override port if specified\n        if args.port != 16000:\n            config.server_port = args.port"
        }],
        "apply": True,
        "commit_message": "Add config.load() call"
    }
)
```

## Root Cause

**File**: `code_analysis/commands/cst_compose_module_command.py`  
**Component**: Range selector replacement logic

When replacing code using `range` selector, the CST parser fails to parse the replacement code snippet. The error suggests that the parser is trying to parse the replacement code as a standalone statement, but it's missing proper context (e.g., it's inside a function body but the parser doesn't know that).

## Impact

- **Severity**: Medium - Workaround available (use function/class selectors instead)  
- **Affected Users**: Anyone trying to use `range` selector for code replacement  
- **Workaround**: Use `function` or `class` selectors, or replace larger blocks that include function boundaries

## Steps to Reproduce

1. Create a Python file with a function containing multiple statements
2. Try to replace a range of lines within the function using `range` selector
3. Observe `ParserSyntaxError` during replacement

## Expected Behavior

The command should successfully replace the specified range of lines with new code.

## Actual Behavior

The command fails with `ParserSyntaxError` before applying changes.

## Proposed Fix

The issue likely occurs because the replacement code is being parsed as a standalone module, but it's actually a fragment that should be parsed in the context of the surrounding code (inside a function, class, etc.).

**Possible solutions**:
1. Parse replacement code in the context of the original code structure
2. Validate that replacement code forms valid statements when inserted
3. Use a different parsing strategy for range replacements

## Environment

- **Package**: code-analysis-server  
- **Python Version**: 3.12  
- **OS**: Linux (6.8.0-90-generic)

## Additional Notes

This is a limitation of the current CST-based replacement mechanism. For now, users should:
- Use `function` or `class` selectors when possible
- Replace entire functions/classes instead of partial ranges
- Use `insert` operation with `position` instead of `replace` for adding code
