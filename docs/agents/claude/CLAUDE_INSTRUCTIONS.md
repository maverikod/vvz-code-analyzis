# Claude instructions — `code_analysis`

> **Scope:** This file is for claude.ai only. It does not replace or modify `.cursorrules`,
> `docs/PROJECT_RULES.md`, or `docs/agents/` files used by Cursor.
> Cursor rules remain authoritative for the Cursor environment.
> Common ground (CR-*, LAYOUT-*, NAME-*, standards) is described in the existing repo docs —
> this file only adds what is specific to Claude's access method.

---

## Project identity (CR-003)

- **Project slug:** `code_analysis`
- **UUID:** `8772a086-688d-4198-a0c4-f03817cc0e6c`
- **Root path:** `/home/vasilyvz/projects/tools/code_analysis`
- **Venv:** `.venv` at project root

Verify UUID via `list_projects` before any write operation. Missing UUID → stop and report.

## How Claude accesses this project

Claude does **not** have direct filesystem access. All operations go through **MCP-Proxy**:

```
MCP-Proxy URL : https://mcp.techsup.od.ua/mcp
server_id     : code-analysis-server
call pattern  : call_server(server_id="code-analysis-server", command="...", params={...})
```

Additional services reachable through the same proxy:
- `embedding-service` — vector embeddings
- `svo-chunker-prod` — semantic chunking

**Direct HTTP to the backend is forbidden.**

## Existing rules Claude must respect

The following files in the repo define the canonical standards. Claude reads them via MCP when needed — never overrides them:

| File | Contents |
|------|----------|
| `docs/PROJECT_RULES.md` | CR-*, LAYOUT-*, NAME-*, profile §0 |
| `docs/agents/project_overlay.md` | Repo-specific paths and restrictions |
| `docs/agents/common_agent_rules.md` | Agent hierarchy and protocol |
| `docs/agents/universal_project_context.md` | Universal project context |
| `docs/standards/` | DRIVER_STANDARD, LOG_IMPORTANCE, PARAMS_VALIDATION, etc. |
| `.cursorrules` | Cursor IDE rules — **do not touch** |

## Sibling projects (CR-002) — do not touch without explicit approval

| Project | UUID |
|---------|------|
| `mcp_proxy_adapter` | `4b331a55-72ed-4e4a-ba35-d0f34ad90110` |
| `vast_srv` | `c86dded6-6f93-4fb0-be54-b6d7b739eeb9` |

## Claude-specific workflow rules

| ID | Rule |
|----|------|
| **CL-01** | All writes go through MCP commands only. No direct filesystem tools. |
| **CL-02** | CST edits: always `preview: true` first, inspect diff, then `apply: true`. Never skip preview. |
| **CL-03** | Before any write: verify UUID via `list_projects`. |
| **CL-04** | Worker lifecycle via `start_worker` / `stop_worker` MCP commands only. |
| **CL-05** | Batch independent read-only calls via `read_only_batch` to minimize round-trips. |
| **CL-06** | Post-edit sequence: `lint_code` → `format_code` → `type_check_code` → `update_indexes`. |
| **CL-07** | Log reads via `view_worker_logs` with `log_id` — not direct file path access. |
| **CL-08** | Never hand-edit `data/*.db` — use MCP commands only. |
| **CL-09** | FAISS index managed via `rebuild_faiss` / `revectorize` only. |
| **CL-10** | Do not create or modify `.cursorrules`, `docs/PROJECT_RULES.md`, or any file under `docs/agents/` except this one (`docs/agents/claude/`). |

## Pre-task checklist

- [ ] Verify UUID via `list_projects`: `8772a086-688d-4198-a0c4-f03817cc0e6c`
- [ ] Check worker health: `get_worker_status` for `vectorization` + `indexing` + `file_watcher`
- [ ] Check DB: `get_database_status`
- [ ] Confirm scope stays inside this project (CR-002)
- [ ] Plan parallel calls where independent — use `read_only_batch` for research phase
- [ ] CST edits: plan preview pass before apply pass
- [ ] Code edits: plan `lint → format → typecheck → update_indexes` sequence

## Language

- Chat: **Russian (ru)**
- All artifacts, code, comments, docstrings, docs: **English (en)**
