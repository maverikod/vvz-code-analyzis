# Bug Report: Search Commands Not Visible in OpenAPI Schema

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-26  
**Status**: ✅ RESOLVED

## Summary

Commands `semantic_search`, `fulltext_search`, `find_classes`, and `list_class_methods` were registered in the server but not visible through MCP Proxy. The commands were missing from the OpenAPI schema that the proxy uses to discover available commands.

## Problem Description

### Symptoms

1. Commands were registered in server logs:
   ```
   Registered custom command: semantic_search
   Registered custom command: fulltext_search
   Registered custom command: list_class_methods
   Registered custom command: find_classes
   ```

2. Commands were NOT visible via MCP Proxy:
   - `mcp_MCP-Proxy-2_help(server_id="code-analysis-server", command="semantic_search")` → Command not found
   - `mcp_MCP-Proxy-2_help(server_id="code-analysis-server", command="fulltext_search")` → Command not found

3. Commands were missing from OpenAPI schema:
   - `/openapi.json` endpoint did not include search commands in `discriminator.mapping`
   - Only 37 commands visible instead of 41

### Impact

- **High**: Search functionality completely unavailable through MCP Proxy
- Users cannot use semantic or full-text search via proxy
- Commands work when called directly on server, but not through proxy interface

## Root Cause Analysis

### Investigation Process

1. **Verified command registration**: Commands were successfully registered in server logs
2. **Checked OpenAPI schema**: Retrieved schema via curl with mTLS, confirmed commands missing
3. **Analyzed adapter code**: Studied `mcp_proxy_adapter/api/openapi/openapi_generator.py`
4. **Added diagnostic logging**: Added logging to see which commands generator sees

### Findings

1. **Commands were registered correctly** via hooks in `code_analysis/hooks.py`
2. **OpenAPI generator** (`CustomOpenAPIGenerator._add_cmd_models`) gets commands from registry:
   ```python
   command_names = list(registry.get_all_commands().keys())
   ```
3. **Generator was called before commands registered**: Initial investigation suggested timing issue
4. **Actual cause**: Server needed full restart after code changes

### Code Flow

```
AppFactory.create_app()
  → register_builtin_commands()
    → hooks.execute_custom_commands_hooks(registry)
      → register_code_analysis_commands(reg)
        → reg.register(SemanticSearchMCPCommand, "custom")
        → reg.register(FulltextSearchMCPCommand, "custom")
        ...
  → app.openapi = lambda: custom_openapi_with_fallback(app)
    → CustomOpenAPIGenerator.generate(app)
      → _add_cmd_models(schema)
        → registry.get_all_commands().keys()  # Should include search commands
```

## Solution

### Changes Made

1. **Added diagnostic logging** to OpenAPI generator:
   ```python
   # In openapi_generator.py line 121
   self.logger.info(f"🔍 OpenAPI Generator: Found {len(command_names)} commands: {sorted(command_names)}")
   ```

2. **Added error handling** in OpenAPI generator:
   ```python
   # In openapi_generator.py lines 125-129, 149-151
   try:
       cmd_class = registry.get_command(cmd_name)
       if cmd_class is None:
           self.logger.warning(f"⚠️ Command {cmd_name} not found in registry, skipping")
           continue
       ...
   except Exception as e:
       self.logger.error(f"❌ Failed to add command {cmd_name} to OpenAPI schema: {e}", exc_info=True)
       continue
   ```

3. **Added registration logging** in hooks:
   ```python
   # In hooks.py
   logger.info(f"✅ Registered search commands: fulltext_search, list_class_methods, find_classes")
   logger.info(f"✅ Registered semantic_search command")
   ```

4. **Server restart**: Full server restart resolved the issue

### Verification

After changes and restart:

1. ✅ OpenAPI generator sees 41 commands (including all search commands)
2. ✅ Commands visible in OpenAPI schema:
   ```json
   "discriminator": {
     "mapping": {
       "semantic_search": "#/components/schemas/CommandRequest_semantic_search",
       "fulltext_search": "#/components/schemas/CommandRequest_fulltext_search",
       "find_classes": "#/components/schemas/CommandRequest_find_classes",
       "list_class_methods": "#/components/schemas/CommandRequest_list_class_methods"
     }
   }
   ```
3. ✅ Commands accessible via MCP Proxy:
   ```python
   mcp_MCP-Proxy-2_help(server_id="code-analysis-server", command="semantic_search")
   # Returns: Success with full command schema
   ```

## Issue with Adapter Updates

### Problem

Changes were made directly to adapter package in `.venv/`:
- `.venv/lib/python3.12/site-packages/mcp_proxy_adapter/api/openapi/openapi_generator.py`

**These changes will be LOST when adapter is updated!**

### Modified Code Locations

1. **Line 121**: Added diagnostic logging
2. **Lines 125-129**: Added null check and warning for missing commands
3. **Lines 149-151**: Added exception handling with error logging

### Recommended Solutions

#### Option 1: Create Custom OpenAPI Generator (Recommended)

Create project-specific generator that extends adapter's generator:

```python
# code_analysis/core/openapi_generator.py
from mcp_proxy_adapter.api.openapi.openapi_generator import CustomOpenAPIGenerator

class CodeAnalysisOpenAPIGenerator(CustomOpenAPIGenerator):
    """Extended OpenAPI generator with additional logging and error handling."""
    
    def _add_cmd_models(self, schema: Dict[str, Any]) -> None:
        """Override with enhanced error handling."""
        # Copy enhanced implementation from modified adapter code
        ...
```

Then override in `main.py`:
```python
from code_analysis.core.openapi_generator import CodeAnalysisOpenAPIGenerator

# After app creation
app.openapi = lambda: CodeAnalysisOpenAPIGenerator().generate(app)
```

#### Option 2: Submit PR to Adapter

Submit improvements to `mcp-proxy-adapter` repository:
- Enhanced error handling
- Diagnostic logging
- Better null checks

#### Option 3: Use Monkey Patching

Patch adapter's generator at runtime:
```python
# In main.py after imports
from mcp_proxy_adapter.api.openapi import openapi_generator

original_add_cmd_models = openapi_generator.CustomOpenAPIGenerator._add_cmd_models

def enhanced_add_cmd_models(self, schema):
    # Enhanced implementation
    ...

openapi_generator.CustomOpenAPIGenerator._add_cmd_models = enhanced_add_cmd_models
```

## Files Modified

### Adapter Package (Will be lost on update)
- `.venv/lib/python3.12/site-packages/mcp_proxy_adapter/api/openapi/openapi_generator.py`

### Project Files (Persistent)
- `code_analysis/hooks.py` - Added registration logging

## Testing

### Test Script

Created `scripts/test_openapi_schema.py` to verify commands in OpenAPI schema:

```bash
python3 scripts/test_openapi_schema.py
```

Expected output:
```
✅ Successfully retrieved OpenAPI schema from localhost
Total commands: 41
Search commands: ['semantic_search', 'fulltext_search', 'list_class_methods', 'find_classes']
```

### Manual Verification

1. ✅ Check server logs for registration:
   ```bash
   tail -100 logs/mcp_server.log | grep "Registered.*search"
   ```

2. ✅ Verify OpenAPI schema:
   ```bash
   curl --cert ... --key ... --cacert ... https://localhost:15000/openapi.json | jq '.components.schemas.CommandRequest.discriminator.mapping | keys | .[] | select(. | contains("search"))'
   ```

3. ✅ Test via MCP Proxy:
   ```python
   mcp_MCP-Proxy-2_help(server_id="code-analysis-server", command="semantic_search")
   ```

## Lessons Learned

1. **Always restart server after code changes** - Commands may not appear until full restart
2. **Don't modify packages in .venv/** - Changes will be lost on update
3. **Add diagnostic logging early** - Helps identify timing and registration issues
4. **Verify OpenAPI schema directly** - Don't rely only on proxy's view

## Related Issues

- Commands registration via hooks
- OpenAPI schema generation timing
- MCP Proxy command discovery mechanism

## Next Steps

1. ✅ **DONE**: Verify commands work via MCP Proxy
2. ⚠️ **TODO**: Create custom OpenAPI generator to preserve changes
3. ⚠️ **TODO**: Submit PR to adapter with improvements (optional)
4. ✅ **DONE**: Document issue and solution

---

**Resolution Date**: 2025-12-26  
**Resolution**: Commands now visible and working via MCP Proxy after server restart. Changes to adapter package need to be preserved via custom generator or PR.

