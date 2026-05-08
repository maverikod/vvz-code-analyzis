# CST Workflow Guide

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Quick decision guide: which CST command to use for a given task, and what to try if the preferred one fails. See [AI_TOOL_USAGE_RULES.md](AI_TOOL_USAGE_RULES.md) for full rules and [commands/cst/](commands/cst/) for command details.

**Reference:** [CST_USABILITY_IMPROVEMENTS.md](reports/CST_USABILITY_IMPROVEMENTS.md) § 6.2, 6.3.

---

## Task → Recommended command → Fallback

| Task | Recommended command | Fallback |
|------|---------------------|----------|
| Replace one import (or one small statement) | `query_cst` with `replace_with` or `code_lines` | `cst_modify_tree` replace (if tree already loaded via `cst_load_file`) |
| Replace multiple imports / statements (different code each) | `query_cst` with `replacements` (list of selector + code) | Multiple `query_cst` calls, or `cst_load_file` → `cst_modify_tree` (multiple replace ops) → `cst_save_tree` |
| Replace function or class body / single block | `cst_modify_tree` replace (after `cst_load_file` + `cst_find_node` or `cst_get_node_by_range`) | `cst_apply_buffer` with selector (e.g. `kind: "function"`, `kind: "method"`) |
| Insert line(s) at module level | `cst_modify_tree` insert with `parent_node_id: "__root__"` | `cst_apply_buffer` with appropriate selector if it fits |
| Insert line(s) inside function/class | `cst_modify_tree` insert with `parent_node_id` = that FunctionDef/ClassDef node_id | `cst_apply_buffer` with selector for the block |
| Single patch by selector (one replace) | `cst_apply_buffer` with one op | `query_cst` with `replace_with`/`code_lines`, or tree-based flow |
| Multiple related edits in one file | `cst_load_file` → `cst_modify_tree` (several ops) → `cst_save_tree` | Multiple `cst_apply_buffer` calls (one file write per call) |
| File has syntax errors (won’t parse) | `replace_file_lines` (project_id, file_path, start_line, end_line, new_lines) | Fix minimal range with text replacement; then retry CST load |
| Create new Python file | `cst_create_file` | Direct write (allowed for new files) |
| List structure / discover blocks | `list_cst_blocks` or `cst_load_file` + `cst_find_node` | `query_cst` (query-only, no replace) |

**Notes:**

- **`cst_apply_buffer`** / **`universal_file_replace`** (Python): selector `kind: "range"` (only `start_line` / `end_line`) finds the **narrowest `BaseStatement` whose line span contains `[start_line, end_line]`** and replaces it. This means: for a single-line call `start_line=end_line=N`, it finds the statement whose span includes line N (even if that statement spans multiple lines). If no statement contains the range, the op goes to `unmatched` — no silent `replaced=1` with empty diff. **Keeps blank lines above** the replaced statement (important for spacing before `class`/`def`). Optional `start_col`/`end_col` for exact character span.
- Use **`project_id`** (from `list_projects` or `projectid` file) for project-scoped commands; see [COMMANDS_GUIDE.md](COMMANDS_GUIDE.md) for schema.
- Prefer **`code_lines`** (array of strings) for multi-line code in `cst_modify_tree` and `query_cst` to avoid JSON escaping.
- For **insert** in `cst_modify_tree`: `parent_node_id` must be a container (Module, FunctionDef, ClassDef); use `__root__` for module level; use the function’s node_id for function body, not its IndentedBlock child.