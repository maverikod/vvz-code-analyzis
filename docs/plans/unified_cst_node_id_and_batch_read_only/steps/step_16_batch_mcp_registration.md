# Step 16 - Expose batch command in MCP layer

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Role:** MCP integration developer.  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Output code file

`code_analysis/commands/ast_mcp_commands.py`

## Goal

Register and expose the new batch read-only command in MCP command surface.

## Required behavior

- New command is discoverable via MCP help/listing.
- Input schema documents command list, threshold behavior, and metadata output format.
- Output schema includes oversize path fields.

## Blackstops

- Do not expose mutating commands through this batch endpoint.
- Do not leave undocumented response fields.

## Success metric

- MCP client can invoke batch command and receive valid responses for small and large payloads.

## Mandatory re-check

- `code_mapper -r code_analysis`
- `black`, `flake8`, `mypy` for touched file
- Verify command appears in help and executes end-to-end.
