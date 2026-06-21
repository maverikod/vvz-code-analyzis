# universal_file_preview

**Command:** `universal_file_preview`  
**Class:** `UniversalFilePreviewCommand`  
**Source:** `code_analysis/commands/universal_file_preview_command.py`  
**Category:** preview

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose

Read-only structured view of any supported project file. Returns navigable blocks with integer **`node_ref`** (`short_id`) values used by `universal_file_edit`.

- Does **not** modify disk, database, or edit sessions (except loading draft state when `session_id` is passed).
- Works **without** an edit session for initial inspection.
- Supported: `.py`, `.json`, `.yaml`, `.yml`, `.md`, `.txt`, `.rst`, `.adoc`, `.jsonl`, `.ndjson`.

**Workflow:** Step 1 (optional before open) for outline navigation. After open, use drill-down here **or** [`universal_file_search`](universal_file_search.md) for XPath on the session CST tree (Python sidecar). See [WORKFLOW.md](WORKFLOW.md).

---

## Arguments

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID from `list_projects` |
| `file_path` | string | **Yes** | Project-relative path; no globs |
| `node_ref` | integer or string | No | Drill-down `short_id` from a prior response; omit for file root |
| `selector` | string or array | No | Slice blocks: `"0:5"`, `"-3:"`, or explicit block ids |
| `preview_lines` | integer | No | Max blocks when selector omitted (default 20) |
| `full_text_max_lines` | integer | No | When file has fewer **source lines** than this (default 200), root preview returns annotated full source on `focus` and every tree node in `blocks`. Set `0` for drilldown only. All formats. |
| `session_id` | string | No | From `universal_file_open` — preview **draft**, not on-disk file |
| `max_chars` | integer | No | **Invalid source only** (`is_invalid`): max chars per `preview_chunk` page |
| `preview_offset` | integer | No | **Invalid source only**: char offset; use `preview_next_offset` from prior page |

Schema source: `get_schema()` on the command class.

---

## Identifier model (`node_ref`)

All marked-tree formats (`.py`, `.json`, `.yaml`, `.md`, `.txt`, …) use the same addressing model:

| Layer | Identifier | Notes |
|-------|------------|--------|
| Preview response | **positive integer `short_id`** | `focus.node_ref` and `blocks[].node_ref` |
| Preview request (canonical) | **integer** | Same value returned earlier |
| Preview request (legacy) | **string alias** | Resolved via `.tree` MAP: UUID4, JSON Pointer, markdown slug, decimal `short_id` string |
| Internal MAP (`.tree` sidecar) | UUID4 `TreeNodeUuid` | **Not** returned in preview JSON |

Omit `node_ref` for file root. Pass the integer from the prior response for drill-down.

**Edit:** pass the same integer `short_id` in `universal_file_edit` (`node_id`, `node_ref`, or `json_pointer` depending on op shape); the server maps to CST stable id, JSON Pointer, or line range internally.

### Parse-error fallback (`is_invalid`)

When JSON/YAML/Python cannot be parsed, preview degrades to **text format** (paragraph/line tree) with `is_invalid: true`.

- Use **`preview_offset`** and **`max_chars`** at file root for pagination.
- **`node_ref`** and **`selector`** are rejected (`REQUIRES_LINE_ADDRESSING`) until syntax is fixed.

---

## Returned data

### Success

- `focus` — current node: `node_kind`, integer `node_ref`, `type`, `attributes`, optional `text` (annotated full source when below `full_text_max_lines`)
- `blocks[]` — child summaries, each with integer `node_ref` for drill-down
- `total_blocks`, `selector_applied`, `mode_notice`
- When `is_invalid`: optional `preview_chunk`, `preview_has_more`, `preview_next_offset`

### Error

Common codes: `UNKNOWN_NODE_REF`, `REQUIRES_LINE_ADDRESSING`, `FILE_LOCKED`, `UNKNOWN_EXTENSION`, `GLOB_IN_FILE_PATH`, `INVALID_SELECTOR_FORM`, `HANDLER_ERROR`.

---

## Examples

**Root preview**

```json
{"project_id": "<uuid>", "file_path": "config/settings.yaml"}
```

**Drill into nested node**

```json
{
  "project_id": "<uuid>",
  "file_path": "config/settings.yaml",
  "node_ref": 2
}
```

Legacy string input (resolved via MAP) is still accepted, e.g. `"node_ref": "/database"`.

**Small file — full annotated tree**

```json
{
  "project_id": "<uuid>",
  "file_path": "src/service.py",
  "full_text_max_lines": 200
}
```

**Drilldown only on large file**

```json
{
  "project_id": "<uuid>",
  "file_path": "src/service.py",
  "full_text_max_lines": 0,
  "preview_lines": 20
}
```

**Preview draft during edit session**

```json
{
  "project_id": "<uuid>",
  "file_path": "src/service.py",
  "session_id": "<from-open>",
  "node_ref": 4
}
```

---

## When to use preview vs session search

| Task | Command |
|------|---------|
| Outline / drill-down one level | `universal_file_preview` (optional `node_ref`) |
| XPath / CSTQuery over whole session tree | `universal_file_search` (requires `session_id`, Python sidecar) |
| Project-wide text or symbol lookup | `search`, project indexes — then open file and preview |

---

## Best practices

- Responses always use **integer `node_ref`**; pass the same integer back for drill-down and edit.
- Legacy aliases (JSON Pointer, MAP UUID4, markdown slug) work on **input only**; do not read UUIDs from sidecar MAP files for API calls.
- Use `full_text_max_lines=0` when you want drilldown blocks only on large files.
- When `is_invalid=true`, use line-based pagination only; fix syntax to restore identifier navigation.
- Re-preview with `session_id` after edits before the next targeted operation.
- Do not use search index line numbers as edit coordinates — they target the index, not the draft.
- For live schema and metadata: `help(command="universal_file_preview")`.

---

## See also

- [universal_file_search.md](universal_file_search.md)
- [universal_file_open.md](universal_file_open.md)
- [PYTHON_EDIT_SEMANTICS.md](PYTHON_EDIT_SEMANTICS.md)
