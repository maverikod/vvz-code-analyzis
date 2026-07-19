# AI Tool Usage Rules

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Overview

This document defines rules for AI models on how to use the code analysis server and related tools in this project.

**CRITICAL PRINCIPLE**: The code-analysis server is a **read/analyze/manage** surface for project files. **Viewing** project files (Python, JSON, YAML, plain text, and other supported formats) goes through **`universal_file_preview`**. **Content editing is not available on the code-analysis server** — it was removed by owner decision; editing lives exclusively on the **ai-editor-server** (see its own documentation). The code-analysis server manipulates files only as whole units (transfer, locks, lifecycle) and analyzes them.

| Task | Where |
|------|-------|
| Inspect / navigate file content | `universal_file_preview` (this server) |
| Search code (index, meaning, disk) | `fulltext_search`, `semantic_search`, `fs_grep`, `search` (this server) |
| Analysis / refactor helpers / quality | analysis commands (this server) |
| Whole-file lifecycle (transfer, locks, delete/move) | file-management commands (this server) |
| **Edit file content** | **ai-editor-server** (not this server) |

**Discovery before reading:** use **`fulltext_search`** (exact tokens in the index) and **`semantic_search`** (meaning-based) to get `file_path` and context, then `universal_file_preview`. See [§2](#2-file-viewing-and-search-workflow).

**Removed from MCP (do not use)** — not registered on the server; not in `help()`:

- Editing sessions: `universal_file_open`, `universal_file_search`, `universal_file_edit`, `universal_file_write`, `universal_file_close`
- Legacy text: `read_project_text_file`, `create_text_file`, `get_file_lines`
- Old per-format editors: `cst_*`, `json_*` tree commands, `list_cst_blocks`, `query_cst`, `cst_apply_buffer`
- Superseded one-shots: `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete`

**Command parameters (source of truth)**: Project-scoped commands use **`project_id`** (UUID from `list_projects` or the `projectid` file in the project root). Authoritative schemas: `help(server_id="code-analysis-server", command="<name>")` via MCP, or `get_schema()` in code. See [COMMANDS_GUIDE.md](COMMANDS_GUIDE.md), [COMMANDS_INDEX.md](COMMANDS_INDEX.md).

**Command metadata vs schema**: Validation and adapter `help` **schema** come from `get_schema()`. Extended AI fields live in `metadata()` — [standards/METADATA_SCHEMA_STANDARD.md](standards/METADATA_SCHEMA_STANDARD.md). Requires **`mcp-proxy-adapter>=8.10.19`**.

**Project-specific rules**: Code under `test_data/` — [TEST_DATA_AI_RULES.md](TEST_DATA_AI_RULES.md) (server-only read for test code; edits via ai-editor-server).

---

## 0. AI Prompt Rules (MANDATORY)

**These rules apply when server `code-analysis-server` is available via MCP Proxy.** When the server is unavailable, notify the user and do not silently read or edit project files with direct IDE tools unless the user explicitly approves fallback.

### 0.0 Quick Reference (For Prompt Insertion)

**IF server is available:**

1. **View any supported project file → `universal_file_preview`**
   - ✅ **View / discover** → `universal_file_preview` (`project_id`, `file_path`, optional `node_ref`)
   - ✅ **Quality checks** → `format_code`, `lint_code`, `type_check_code`
   - ✅ **Project analysis** → `comprehensive_analysis`, `get_code_entity_info`, etc.
   - ➡️ **Edit content** → ai-editor-server (not this server)
   - ❌ **FORBIDDEN**: `universal_file_open/search/edit/write/close`, `cst_*`, `json_*` tree MCP commands, legacy `read_project_text_file` / `create_text_file` / `get_file_lines`
   - ❌ **FORBIDDEN**: Direct file tools for `test_data/` code (see TEST_DATA_AI_RULES)

2. **Search inside or across files** (read-only):
   - ✅ **`fulltext_search`** — exact tokens / names in the DB index (FTS5, BM25)
   - ✅ **`semantic_search`** — meaning-similar chunks (embeddings + FAISS)
   - ✅ **`search`** — unified paginated cross search (fulltext + optional semantic/grep)
   - ✅ `fs_grep` — regex on disk when the index is missing or you need raw bytes
   - ✅ `search_ast_nodes`, `find_usages`, `get_ast`, … — structure and references  
   See [§2.9 Fulltext and semantic search](#29-fulltext-and-semantic-search).

3. **Error handling → USER DECISION**
   - Report server errors immediately; wait before using non-server fallbacks.

### 0.1 Core Principle

- Use server tools when available (validation, backups, handler routing).
- Report ALL errors to the user; do not silently switch to direct file tools.

### 0.2 Tool Selection (MANDATORY WHEN SERVER AVAILABLE)

| Task | Command(s) |
|------|----------------|
| See file structure / snippet | `universal_file_preview` |
| Change file content | ai-editor-server (not this server) |
| Find exact text / symbol names (indexed) | `fulltext_search` |
| Find by meaning / concept | `semantic_search` |
| Unified paginated cross search | `search` |
| Find regex on disk (no index) | `fs_grep` |
| Split / extract refactor | `split_file_to_package`, `split_class`, … |
| Format / lint / types | `format_code`, `lint_code`, `type_check_code` |

### 0.3 Error Handling and Fallback

1. Report exact error, command name, and params to the user.
2. Do **not** auto-fallback to direct file tools on server errors.
3. User decides: retry, fix params, fix code, or approve rare direct access.

### 0.4 When Direct Tools Are Allowed (EXCEPTIONS ONLY)

- ✅ Editing **this repository’s** `code_analysis/` package via normal IDE tools (not `test_data/`).
- ✅ Non-project assets (docs outside server scope) when no `project_id` applies.
- ❌ Reading existing project files under a registered `project_id` with direct tools when the server is up and preview suffices.

### 0.5 Quick Decision Tree

```
Is code-analysis-server available?
├─ NO  → Notify user → fallback only with approval
└─ YES → Need to read a project file?
    ├─ YES → universal_file_preview (read)
    ├─ Need to change content? → ai-editor-server
    └─ NO  → Search / analysis / refactor commands as appropriate
```

---

## 1. Tool Priority Rules

### 1.1 Primary Interface: MCP

**Priority:**

1. ✅ **MCP** — `call_server(server_id="code-analysis-server", copy_number=1, command="...", params={...})`
2. ⚠️ **CLI** — fallback for humans or when MCP is unavailable

Use **`project_id`** in params (from `list_projects`), not host `root_dir`, unless the schema explicitly allows otherwise.

**Example:**

```python
call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="universal_file_preview",
    params={
        "project_id": "<uuid-from-list_projects>",
        "file_path": "src/module.py",
    },
)
```

### 1.2 Server Management

Restart after changes under `code_analysis/` or new command registration:

```bash
cd /path/to/code_analysis
source .venv/bin/activate
casmgr --config config.json restart
```

---

## 2. File Viewing and Search Workflow

**Canonical docs:** [commands/file_editing/README.md](commands/file_editing/README.md) (preview; editing history)

### 2.1 Preview (read-only)

**Command:** `universal_file_preview`

- Works without any session; the only content-view command on this server.
- Omit `node_ref` for root view; pass `node_ref` from a previous response to drill down.
- `node_ref` shape depends on file type: CST stable UUID for Python, JSON Pointer (e.g. `/timeout`) for JSON/YAML, zero-based line index string for plain text.

```python
call_server(
    command="universal_file_preview",
    params={
        "project_id": "<uuid>",
        "file_path": "config/settings.yaml",
        "node_ref": "/database",  # optional
    },
)
```

### 2.2 Editing (not on this server)

Content editing is performed on the **ai-editor-server**, which drives the code-analysis server's whole-file lifecycle (locks, transfer, upload) underneath. Do not attempt `universal_file_open/edit/write/close` here — the commands are not registered and will fail with command-not-found.

### 2.7 After external edits — quality and indexes

1. `format_code` / `lint_code` / `type_check_code` on `file_path`
2. `comprehensive_analysis` after logically completed steps
3. Run `update_indexes` if a project-wide rebuild is needed after large external changes

### 2.8 Refactoring large Python files

Structural splits use dedicated MCP commands (`split_file_to_package`, `split_class`, `extract_superclass`, `file_structure`) — not raw text editing. After refactor commands change files, use `universal_file_preview` to inspect results; manual content edits go through the ai-editor-server.

### 2.9 Fulltext and semantic search

Use indexed search to **discover** where to read. Search commands do **not** modify files. After you have `file_path` (and optionally `line` from a hit), continue with `universal_file_preview`.

**Detailed command docs:** [commands/search/fulltext_search.md](commands/search/fulltext_search.md), [commands/analysis/semantic_search.md](commands/analysis/semantic_search.md).

#### When to use which

| Command | Best for | Index / deps | Typical query |
|---------|----------|--------------|---------------|
| **`fulltext_search`** | Exact words, identifiers, `def foo`, class names, strings in code/docstrings | SQLite **FTS5** (`code_content_fts`); project DB must be built | `"ValidationError"`, `"def execute"`, `"MyClass"` |
| **`semantic_search`** | Concepts, paraphrases, “how is X done here?” without exact wording | **FAISS** + embedding service; run `update_indexes` / vectorization first | `"retry database connection"`, `"parse config yaml"` |
| **`search`** | Unified paginated cross search (fulltext always; semantic/grep opt-in) | Same as above per phase | any of the above |
| **`fs_grep`** | Regex, unindexed paths, “what’s on disk right now” | None (scans files) | `pattern="register\\("`, `file_pattern="**/*.py"` |

**Rule of thumb:** start with **`fulltext_search`** for known symbols or literals; use **`semantic_search`** when you do not know the exact name; use **`fs_grep`** if FTS returns nothing but the file exists on disk, or you need line-accurate regex outside the index.

#### Prerequisites

1. `list_projects` → copy **`project_id`** (UUID).
2. Project must be **indexed**:
   - Empty or stale **`fulltext_search`** → run `update_indexes` with the same `project_id`, then retry.
   - **`semantic_search`** errors (`FAISS_INDEX_NOT_FOUND`, `EMBEDDING_SERVICE_ERROR`) → ensure indexes/vectors are built and embedding service is configured; see server logs.
3. After large external file changes, run `update_indexes` before relying on search again.

#### `fulltext_search`

**Purpose:** BM25-ranked search over indexed **chunk text**, docstrings, entity names, and symbol rows (variables, attributes).

**Parameters** (see `help` for the live schema):

| Parameter | Required | Notes |
|-----------|----------|--------|
| `project_id` | Yes | Project UUID |
| `query` | Yes | Free text; FTS tokenization (partial words, case-insensitive) |
| `entity_type` | No | Filter: `file`, `class`, `method`, `function`, `variable`, `attribute` |
| `limit` | No | Default **20** |

**Success payload (per hit):** `file_path`, `line`, `chunk_text`, `chunk_type`, `rank` (lower = more relevant), `chunk_uuid`.

**Example (MCP):**

```python
call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="fulltext_search",
    params={
        "project_id": "<uuid>",
        "query": "BaseMCPCommand",
        "entity_type": "class",
        "limit": 15,
    },
)
```

**Use cases:**

- Find all references to an error class or constant name.
- Locate functions whose docstring or body mentions a keyword.
- Narrow to classes: `entity_type="class"`, query=`"BaseMCPCommand"`.

#### `semantic_search`

**Purpose:** Find code chunks **semantically similar** to the natural-language query (embedding cosine similarity via FAISS).

**Parameters:**

| Parameter | Required | Notes |
|-----------|----------|--------|
| `project_id` | Yes | Project UUID |
| `query` | Yes | Natural language; **English** often matches indexed metadata best |
| `limit` | No | Default **10**, clamped **1–100** |
| `min_score` | No | Similarity threshold **0.0–1.0** (higher = stricter) |

**Success payload (per hit):** `file_path`, `line`, `text`, `score` (higher = better), `distance`, `chunk_type`, `chunk_uuid`.

**Example (MCP):**

```python
call_server(
    server_id="code-analysis-server",
    copy_number=1,
    command="semantic_search",
    params={
        "project_id": "<uuid>",
        "query": "validate command parameters against json schema",
        "limit": 20,
        "min_score": 0.55,
    },
)
```

**Use cases:**

- Explore unfamiliar codebase areas by intent (“where is backup before write?”).
- Find analogous implementations when names differ.
- Rank candidates with `min_score` to drop weak matches.

#### Combined workflow: search → preview

```
list_projects
    → fulltext_search / semantic_search / search / fs_grep
    → note file_path (+ line) from results
    → universal_file_preview(project_id, file_path)   # optional node_ref drill-down
    → (changes needed? → ai-editor-server)
```

**Tips:**

- Run **`fulltext_search`** and **`semantic_search`** with the same `project_id` for complementary hits (exact + conceptual).
- From a hit’s `line`, open preview at file root first; use surrounding context in `chunk_text` / `text` to choose what to inspect next.
- Search does not replace **`find_usages`** / **`find_dependencies`** for precise reference graphs—use those when you need symbol-level edges, not text similarity.

---

## 3. Code Validation Rules

### 3.1 Automatic validation

- Content writes performed through the ai-editor-server run project validators before persisting; failed validation is reported by that server.

### 3.2 Manual checks

```python
format_code(project_id=..., file_path=...)
lint_code(project_id=..., file_path=...)
type_check_code(project_id=..., file_path=...)
```

### 3.3 Docstrings

Canonical standard: [standards/PYTHON_DOCSTRING_STANDARD.md](standards/PYTHON_DOCSTRING_STANDARD.md). Plan new Python nodes with docstrings and type hints before commit.

---

## 4. File Organization Rules

### 4.1 Directory structure

| Content | Location |
|---------|----------|
| Source | `code_analysis/` |
| Docs | `docs/` |
| Scripts | `scripts/` |
| Logs | `logs/` |
| Data | `data/` |
| Pytest | `tests/` |
| Test projects | `test_data/` |

### 4.2 File size

- Prefer files **under 400 lines**; use `list_long_files` / `comprehensive_analysis` to detect violations.
- Split with MCP refactor commands rather than manual copy-paste.

---

## 5. Code Analysis Workflow

### 5.1 Before changes

1. `list_projects` → `project_id`
2. Locate targets: `fulltext_search` / `semantic_search` (indexed) or `fs_grep` (disk); then `universal_file_preview` or `get_code_entity_info`
3. `file_structure` before large refactors

### 5.2 After changes (made via ai-editor-server or refactor commands)

1. `format_code`, `lint_code`, `type_check_code`
2. `comprehensive_analysis` when appropriate
3. `update_indexes` if search results look stale

---

## 6. Available MCP Commands (summary)

### 6.1 Universal file (view) — **PRIMARY FOR FILE CONTENT VIEWING**

Per-command docs: [commands/file_editing/](commands/file_editing/)

| Command | Purpose |
|---------|---------|
| `universal_file_preview` | Read-only navigation and snippets (the only registered `universal_file_*` command) |

Content editing: ai-editor-server.

### 6.2 Search (read-only; no session required)

| Command | Purpose |
|---------|---------|
| **`fulltext_search`** | FTS5 over indexed code, docstrings, names — [fulltext_search.md](commands/search/fulltext_search.md) |
| **`semantic_search`** | Embedding similarity (FAISS) — [semantic_search.md](commands/analysis/semantic_search.md) |
| **`search`** | Unified paginated cross search (fulltext + optional semantic/grep) |
| `fs_grep` | Regex on disk (no DB index) |
| `list_yaml_blocks` | YAML node listing in one file |
| `search_ast_nodes` | AST node search by type |
| `find_usages` / `find_dependencies` | Reference graph |

Use search commands to **find** locations; use **`universal_file_preview`** to **view** content. See [§2.9](#29-fulltext-and-semantic-search).

### 6.3 Analysis, AST, refactor, quality

- Analysis: `comprehensive_analysis`, `analyze_complexity`, `find_duplicates`, `update_indexes`, …
- AST: `get_ast`, `list_code_entities`, `get_code_entity_info`, `list_project_files`, …
- Refactor: `file_structure`, `split_class`, `extract_superclass`, `split_file_to_package`
- Quality: `format_code`, `lint_code`, `type_check_code`

### 6.4 File management (lifecycle, not content editing)

`delete_file`, `fs_copy`, `fs_move`, `fs_remove`, trash/restore commands, `project_file_*` locks and transfers — see `help` per command.

### 6.5 Removed from MCP catalog (historical)

Do not document or call via MCP: `universal_file_open`, `universal_file_search`, `universal_file_edit`, `universal_file_write`, `universal_file_close`, `cst_load_file`, `cst_modify_tree`, `cst_save_tree`, `cst_apply_buffer`, `query_cst`, `list_cst_blocks`, `json_load_file`, …, `read_project_text_file`, `write_project_text_lines`, `create_text_file`, `get_file_lines`, `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete`.

---

## 7. Error Handling

### 7.1 Process

1. Read error code and message from server response.
2. Check `logs/` if needed.
3. Fix params per the command schema (`help`).
4. Restart server after `code_analysis/` code changes.
5. Do not continue with broken committed state.

### 7.2 Common situations

| Situation | Action |
|-----------|--------|
| Wrong `node_ref` / no match in preview | Re-run `universal_file_preview` from the root view |
| Command not found for `universal_file_open/edit/write/close` | Expected — editing moved to ai-editor-server |
| Need find-before-read | `fulltext_search` / `semantic_search` / `fs_grep` → `universal_file_preview` at `file_path` |
| Search results stale or empty | `update_indexes` with the same `project_id`, then retry |

Do **not** fall back to deprecated `cst_*` or legacy text commands.

---

## 8. Code Writing Standards

### 8.1 Docstrings and types

Follow [standards/PYTHON_DOCSTRING_STANDARD.md](standards/PYTHON_DOCSTRING_STANDARD.md). File, class, and public method docstrings are enforced on Python commit when validation is enabled.

---

## 9. Workflow Examples

### 9.1 Inspect a YAML key

```python
# 1. Preview root
universal_file_preview(project_id, file_path="config/app.yaml")
# 2. Preview child
universal_file_preview(project_id, file_path="config/app.yaml", node_ref="/database")
```

### 9.2 Fulltext then semantic (discover APIs)

```python
# Exact symbol or string
ft = call_server(
    command="fulltext_search",
    params={"project_id": pid, "query": "EditSession", "entity_type": "class", "limit": 10},
)
# Same topic, different wording
sem = call_server(
    command="semantic_search",
    params={"project_id": pid, "query": "in-memory draft for file editing", "limit": 10, "min_score": 0.5},
)
# Pick file_path from ft or sem results["data"]["results"]
call_server(command="universal_file_preview", params={"project_id": pid, "file_path": hit["file_path"]})
```

### 9.3 Find then inspect

```python
# Indexed literal
fulltext_search(project_id, query="TODO", limit=30)
# Or disk regex if needed
fs_grep(project_id, pattern="TODO", file_pattern="**/*.py", max_results=20)
# For each hit: universal_file_preview; changes go through ai-editor-server
```

---

## 10. Technology Notes

### 10.1 Structured views, not raw dumps

Preview returns **stable node references** (UUID, JSON Pointer, or line index) for structured navigation. Content mutation against those references happens on the ai-editor-server.

### 10.2 test_data

All reads of code under `test_data/` must use the server (MCP), per [TEST_DATA_AI_RULES.md](TEST_DATA_AI_RULES.md); content edits go through the ai-editor-server.

---

## 11. Best Practices Summary

### 11.1 Always do

- ✅ MCP as primary interface
- ✅ `fulltext_search` / `semantic_search` (or `fs_grep`) before reading unknown code; `update_indexes` if search is empty
- ✅ `universal_file_preview` for content viewing
- ✅ `format_code` / `lint_code` / `type_check_code` after external edits
- ✅ Report errors; wait for user on fallback
- ✅ Restart server after changing `code_analysis/`

### 11.2 Never do

- ❌ `universal_file_open/search/edit/write/close` — not registered here (editing is on ai-editor-server)
- ❌ `cst_*`, legacy text commands, or unregistered `universal_file_read/save/replace/delete`
- ❌ Ignore validation errors reported by the editing server
- ❌ Use CLI for routine automation when MCP works

---

## 12. Quick Reference

| Goal | Commands |
|------|----------|
| **View file** | `universal_file_preview` |
| **Edit file** | ai-editor-server (not this server) |
| **Find exact text (index)** | `fulltext_search` |
| **Find by meaning** | `semantic_search` |
| **Unified cross search** | `search` |
| **Find regex on disk** | `fs_grep` |
| **Quality** | `format_code`, `lint_code`, `type_check_code` |
| **Project health** | `comprehensive_analysis` |

**Interface priority:** MCP `call_server` → CLI (fallback).

---

**Remember**: This project is built for AI-driven development through the code-analysis server. File **viewing** goes through **`universal_file_preview`**; file **content editing** goes through the **ai-editor-server** — never legacy CST or plain-text MCP commands on this server.
