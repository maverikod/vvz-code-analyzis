# CST commands: gap analysis — replacing direct file reading

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Purpose

Identify what is missing in existing CST (and related) commands so that **direct reading of project files** (e.g. to inspect a line or fix a syntax error) can be replaced by server commands only.

## Existing CST-related commands (summary)

| Command | Input | Output | Requires valid syntax? |
|--------|--------|--------|------------------------|
| **cst_load_file** | project_id, file_path | tree_id, nodes | Yes (fails on SyntaxError; has heuristic fix but not always applied/written back) |
| **cst_get_node_by_range** | tree_id, start_line, end_line | node (or nodes) covering range | N/A — needs tree_id (file already loaded) |
| **cst_get_node_info** | tree_id, node_id | metadata, children, parent (optional) | N/A — works on tree |
| **cst_find_node** | tree_id, query | matches (node_ids, metadata) | N/A — works on tree |
| **cst_modify_tree** | tree_id, operations | — | N/A — works on tree |
| **cst_save_tree** | tree_id, project_id, file_path | — | N/A — saves tree to file |
| **query_cst** | project_id/root_dir, file_path, selector | matches | **Yes** — parses file from disk |
| **list_cst_blocks** | project_id, file_path | blocks with stable IDs | **Yes** — parses file from disk |
| **compose_cst_module** | project_id, file_path, tree_id or ops | — | Depends (can apply ops; if tree from broken file, load already failed) |

## What direct file reading is used for (in practice)

1. **See content around a given line** (e.g. lines 165–172) to understand a syntax/lint error and plan a fix.  
2. **Understand “context” of a line** — which block/function/class it belongs to (e.g. “parent node of line 168”).

## Gaps

### 1. When the file has a syntax error

- **cst_load_file** fails (or applies a heuristic fix but may not write it back; tree may not be available).
- **query_cst** and **list_cst_blocks** parse the file from disk → they also fail on invalid syntax.
- **Result:** There is **no command** that returns “raw content” (e.g. lines N–M) or “structure at line X” for a file that does not parse.

So to replace direct reading in the “syntax error at line 168” scenario we need at least one of:

- **Option A — Raw lines (non-CST):**  
  A command that returns the content of a line range **without parsing**, e.g.  
  `get_file_lines(project_id, file_path, start_line, end_line)`  
  → returns `{"lines": ["line1", "line2", ...], "start_line": N, "end_line": M}`.  
  This replaces “read file and show lines around 168” and does not require valid Python.

- **Option B — Robust load + write-back:**  
  Ensure **cst_load_file** always applies the syntax-error heuristic (comment bad line + `pass` + TODO), writes the fixed source back to the file (or to a temp path the client can use), and returns a **tree_id**. Then the client can use CST commands (e.g. node at line, parent) on that tree.  
  This still does not help if we want to “only read” without modifying the file; it helps for “fix then inspect”.

### 2. When the tree is loaded (valid syntax)

To get **“node that contains line X”** we already have:

- **cst_get_node_by_range**(tree_id, start_line=X, end_line=X)  
  → returns the (smallest) node that spans that line.

To get **“parent of the node at line X”** we can do:

1. **cst_get_node_by_range**(tree_id, 168, 168) → node_id  
2. **cst_get_node_info**(tree_id, node_id, include_parent=True) → parent in `data["parent"]`

So “parent node for a given line” is **already possible in two calls**. What is missing is only convenience and a single round-trip:

- **Option C — Single command: “node and parent for line”**  
  A command that returns both the node at a line and its parent in one go, e.g.  
  `cst_get_node_at_line(tree_id, line)` or `cst_get_parent_node_for_line(tree_id, line)`  
  returning e.g. `node_id`, `node` (metadata), `parent_id`, `parent` (metadata).  
  This avoids two MCP round-trips and makes the intent explicit.

## Recommendation

1. **To replace direct file reading when there is a syntax error:**  
   Add a **get_file_lines**-style command (project_id, file_path, start_line, end_line) that returns raw lines **without** parsing. This is the minimal addition that covers “show me lines around the error” without touching CST or the file content.

2. **To make “parent of line” easier when the tree exists:**  
   Add **cst_get_node_at_line** (or **cst_get_parent_node_for_line**) that, given tree_id and line, returns the node spanning that line and its parent in one response. This does not add new capabilities but reduces round-trips and clarifies intent.

3. **Optional:** Revisit **cst_load_file** so that when it applies the syntax-error fix (comment + pass), it consistently writes the fix back and returns tree_id, so that after “fix on load” the client can use **cst_get_node_by_range** + **cst_get_node_info(parent)** or the new “node at line + parent” command without ever reading the file directly.

## Summary table

| Need | Today | Missing |
|------|--------|--------|
| Raw lines N–M (no parse) | — | **get_file_lines**(project_id, file_path, start_line, end_line) |
| Node at line (tree loaded) | cst_get_node_by_range(tree_id, L, L) | — (already there) |
| Parent of node at line (tree loaded) | get_node_by_range → get_node_info(..., include_parent=True) | One convenience command: **cst_get_node_at_line** / **cst_get_parent_node_for_line** (node + parent in one call) |
| Any structure when file has syntax error | — | Either get_file_lines (read-only) or guaranteed cst_load_file fix + write-back (then use tree) |
