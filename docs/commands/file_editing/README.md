# File editing commands (historical) and file preview

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Current state (owner decision, 2026-07):** the code-analysis server no longer
registers content-editing commands. The only registered `universal_file_*`
command is [`universal_file_preview`](universal_file_preview.md) (read-only
navigation and snippets). **Content editing lives exclusively on the
ai-editor-server** — see that server's documentation.

| Step | Command | Status |
|------|---------|--------|
| View | [`universal_file_preview`](universal_file_preview.md) | ✅ Registered |
| Open / search / edit / write / close | [`universal_file_open`](universal_file_open.md), [`universal_file_search`](universal_file_search.md), [`universal_file_edit`](universal_file_edit.md), [`universal_file_write`](universal_file_write.md), [`universal_file_close`](universal_file_close.md) | ❌ Removed from this server (docs kept as historical reference; the workflow now lives on ai-editor-server) |

Historical workflow description: **[WORKFLOW.md](WORKFLOW.md)** ·
**[PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md)** (kept for the
ai-editor-server implementation, which reuses these semantics).

## AI model rules (short)

- Routing standard: [standards/FILE_EDIT_WORKFLOW.yaml](../../standards/FILE_EDIT_WORKFLOW.yaml)
- Extended rules: [AI_TOOL_USAGE_RULES.md](../../AI_TOOL_USAGE_RULES.md)
- Live parameter schemas: `help(server_id="code-analysis-server", command="<name>")`

## Do not use for editing (removed MCP commands)

| Removed / legacy | Use instead |
|------------------|-------------|
| `universal_file_open` → `edit` → `write` → `close` | ai-editor-server |
| `cst_load_file` → `cst_modify_tree` → `cst_save_tree` | ai-editor-server |
| `query_cst`, `list_cst_blocks`, `cst_apply_buffer` | ai-editor-server |
| `cst_find_node` (legacy `tree_id` XPath) | `universal_file_preview` drill-down (read) |
| `read_project_text_file`, `write_project_text_lines` | `universal_file_preview` (read) / ai-editor-server (write) |
| `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete` | `universal_file_preview` (read) / ai-editor-server (write) |

CST command docs under [../cst/](../cst/) describe **internal/server developer APIs** still registered for tooling — not the MCP editing path for AI agents.
