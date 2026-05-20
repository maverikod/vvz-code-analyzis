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
**bash_tool / filesystem tools are forbidden for project file access.**

## Existing rules Claude must respect

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
| **CL-01** | All reads and writes go through MCP commands only. No bash_tool, no direct filesystem. |
| **CL-02** | CST edits: always preview first (`universal_file_write` with preview), inspect diff, then commit. Never skip preview. |
| **CL-03** | Before any write: verify UUID via `list_projects`. |
| **CL-04** | Worker lifecycle via `start_worker` / `stop_worker` MCP commands only. |
| **CL-05** | Batch independent read-only calls via `read_only_batch` to minimize round-trips. |
| **CL-06** | Post-edit sequence for code files: `lint_code` → `format_code` → `type_check_code` → `update_indexes`. |
| **CL-07** | Log reads via `view_worker_logs` with `log_id`. |
| **CL-08** | Never hand-edit `data/*.db` — use MCP commands only. |
| **CL-09** | FAISS index managed via `rebuild_faiss` / `revectorize` only. |
| **CL-10** | Do not modify `.cursorrules`, `docs/PROJECT_RULES.md`, or any file under `docs/agents/` except `docs/agents/claude/`. |
| **CL-11** | Before using any MCP command for the first time in a session — read its `help` first. Never guess parameters. |

## File read/write — universal edit workflow

All file reads and writes use the **universal file edit workflow**. This is the only
correct method. Commands `universal_file_save`, `create_text_file`, `replace_file_lines`,
`write_project_text_lines` are **obsolete** — do not use them.

### Step 1 — Read: `universal_file_preview`

Use to read file content and obtain `node_ref` values before editing.

```
universal_file_preview(project_id, file_path)
```

### Step 2 — Open: `universal_file_open`

Opens an existing file or creates a new one (`create=true`).
Returns `session_id` and `format_group` (text | tree-temp | sidecar).

```
universal_file_open(project_id, file_path, create=false)
```

- `create=true` — creates the file if it does not exist.
- For `.py`: `initial_content` required when `create=true`.
- For `.md`, `.txt`, `.yaml`, `.json` etc: file is created empty; content is added via `universal_file_edit`.

### Step 3 — Edit: `universal_file_edit`

Applies operations to the in-memory draft. Never touches disk.
Operation shape depends on `format_group`:

**text** (`.md`, `.txt`, `.rst`, `.adoc`):
```json
{"type": "insert", "position": "last", "content": "line to append"}
{"type": "replace", "start_line": 3, "end_line": 5, "content": "new content"}
{"type": "delete", "start_line": 3, "end_line": 5}
```

**tree-temp** (`.json`, `.yaml`, `.yml`):
```json
{"type": "replace", "json_pointer": "/key", "value": "new value"}
{"type": "insert", "parent_json_pointer": "/list/-", "value": "item"}
```

**sidecar** (`.py`, `.pyi`, `.pyw`):
```json
{"type": "replace", "node_id": "<UUID from universal_file_preview>", "code_lines": ["def f(): ...", "    pass"]}
```

### Step 4 — Write: `universal_file_write`

Two-phase: first call = preview diff, second call = commit to disk.

```
universal_file_write(project_id, session_id)          # first: preview
universal_file_write(project_id, session_id)          # second: commit
```

**CL-02 applies here:** always inspect the diff from the first call before committing.

### Step 5 — Close: `universal_file_close`

Always call after write (or on abort). Releases session and cleans up artefacts.

```
universal_file_close(project_id, session_id)
```

## Pre-task checklist

- [ ] Verify UUID via `list_projects`: `8772a086-688d-4198-a0c4-f03817cc0e6c`
- [ ] Check worker health: `get_worker_status`
- [ ] Check DB: `get_database_status`
- [ ] Confirm scope stays inside this project (CR-002)
- [ ] For any unfamiliar command: read `help(cmdname=...)` before calling
- [ ] For CST edits: plan preview pass before commit pass
- [ ] For code edits: plan `lint → format → typecheck → update_indexes` sequence

## Language

- Chat: **Russian (ru)**
- All artifacts, code, comments, docstrings, docs: **English (en)**
