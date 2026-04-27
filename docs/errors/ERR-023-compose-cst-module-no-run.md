## 23. compose_cst_module -> HTTP 500: ComposeCSTModuleCommand has no attribute 'run'

Discovered: 2026-04-28
Log: logs/mcp_proxy_adapter_error.log
First occurrence: 2026-04-28 01:23:05
Reproducibility: 100% -- every call to compose_cst_module via MCP.

Status: FIXED (verified 2026-04-28 after server restart)

Symptom:

  ERROR - Unhandled error in command 'compose_cst_module':
    type object 'ComposeCSTModuleCommand' has no attribute 'run'
  Traceback:
    File ".../mcp_proxy_adapter/api/handlers.py", line 757, in execute_command
      command_class.run(**params, context=context)
  AttributeError: type object 'ComposeCSTModuleCommand' has no attribute 'run'

Root cause:

The adapter calls command_class.run(...) -- a classmethod defined only in BaseMCPCommand.
ComposeCSTModuleCommand was declared without inheritance:

  # WAS (broken):
  class ComposeCSTModuleCommand:

  # NOW (fixed):
  class ComposeCSTModuleCommand(BaseMCPCommand):

File: code_analysis/commands/cst_compose_module_command.py, line ~57.

Fix applied:
  class ComposeCSTModuleCommand(BaseMCPCommand):

Verification (2026-04-28 01:34 after server restart):
  - cst_load_file shows: class ComposeCSTModuleCommand(BaseMCPCommand)
  - compose_cst_module with apply=false returns HTTP 200, success=true, diff included
  - No AttributeError in mcp_proxy_adapter_error.log
