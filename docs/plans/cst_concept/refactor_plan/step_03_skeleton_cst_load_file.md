# Step 3: Skeleton response in `cst_load_file` (collapsed branches)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Plan index:** [REFACTOR_PLAN.md](../REFACTOR_PLAN.md)

---

## Goal

By default (or via flag) return a **skeleton** that matches what a modern editor shows with **collapsed branches**: full structure, no implementation bodies. The model sees full signatures, docstrings, and body placeholders (comment + `pass`) for all methods/functions; module-level variables and expressions are full.

## File to modify

`code_analysis/commands/cst_load_file_command.py`

## Behaviour

- Add parameter **`return_format: "full" | "skeleton"`** (default `"full"` for backward compatibility). Do not add a separate boolean; use this single enum for clarity.
- When **skeleton**: after building the tree, build a representation where:
  - **Module level:** file docstring, module-level variables, module-level expressions — **full** (full text).
  - **Each function/method:** full signature (full parameter list), docstring, and **body placeholder** — the body is replaced by a single comment (e.g. `# Call node body to see code`) and `pass`. So every callable looks like:
    ```python
    def fun(self, full_param_list):
        """Docstring of the method."""
        # Call node body to see code
        pass
    ```
  Return `tree_id` + this structure (no full node list in skeleton mode). Reuse existing tree build; only change response shape.
- **Skeleton and syntax errors:** The skeleton is built from the tree that the load command produces. If the loader applies the syntax-error path (comment-out + pass in memory), the skeleton is built from that in-memory fixed tree.
- **Optional selector in the same request:** Together with the load (file read) request, the client can pass an optional **selector**. The selector can be either:
  - **An XPath-like expression (CSTQuery selector string)** — same syntax as in `query_cst` and `cst_find_node` (see `code_analysis/cst_query/parser.py`, `tree_finder.find_nodes(..., search_type="xpath")`). The server evaluates the selector against the tree and includes the content of all matching nodes in the response.
  - **A list of node identifiers (node_ids)** — UUIDs that exist in the tree (e.g. from a previous skeleton response). The server looks up each node_id in the tree’s metadata and includes their content in the response.
  When present, the response includes the structure (skeleton or full) **and** the content of the nodes matching the selector (with requested scope: code, children, etc.) in one call. Reuse existing CSTQuery execution (`find_nodes` with xpath, `query_source`) for the string form; use direct `tree.metadata_map` / `get_node_metadata` for the list-of-identifiers form.

## References

- Concept §1.3, §2.1 (selector in load), §6.1, §6.7: [CST_CONCEPT_AND_PIPELINE.md](../CST_CONCEPT_AND_PIPELINE.md)
- XPath-like selector in project: `code_analysis/cst_query/` (parser, executor), `code_analysis/core/cst_tree/tree_finder.py` (`find_nodes(..., search_type="xpath")`), `code_analysis/commands/query_cst_command.py`, `code_analysis/commands/cst_find_node_command.py`.

## Optional

Helper in `code_analysis/core/cst_tree/` (e.g. `skeleton_from_tree(tree)`) if logic is large; then step “1 file” is the command file that calls it.

## Success metrics

- With return_format=full (default): behaviour unchanged (tree_id + nodes).
- With return_format=skeleton: response has tree_id + structure (collapsed view: full signatures, docstrings, body = comment + pass for callables; full module-level content).
- File with syntax error (comment+pass path): skeleton still possible from fixed tree.
- With optional selector (CSTQuery string or list of node_ids) in the load request, response includes structure plus content of the selected nodes in one call.

## Post-step checks

- Search and fix: incomplete code, TODO, ellipsis/syntax violations, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations from project/plan rules.
- Run `code_mapper -r <project_code_dir>` and fix all reported errors.
- Run `mypy`, `flake8`, `black` and fix all reported issues.
