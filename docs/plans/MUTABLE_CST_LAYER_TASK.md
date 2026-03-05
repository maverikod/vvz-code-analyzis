# Task: Mutable CST layer for batch edits

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Goal

Introduce a **mutable tree layer** between LibCST and our edit operations. LibCST parses and provides the initial tree; search finds nodes; our layer applies replacements/inserts **in place, bottom-to-top**; then we hand the result back (serialize to source or build LibCST tree) for validation/codegen. This avoids LibCST’s immutable “new tree per edit” cost and makes batch replace/insert reliable.

---

## Context

- LibCST builds an **immutable** CST: every edit returns a new tree (with structural sharing). After one replace, `node_map` and metadata still point at nodes from the **old** tree; the next operation cannot resolve the next node correctly in the **new** tree without re-indexing or re-resolving by position.
- Batch replace/insert (e.g. add docstrings to many methods) therefore fails after the first operation.
- Code structure is a **tree** (no backward jumps). Edits are local: “replace this node”, “insert here”. A mutable representation allows true in-place edits and keeps the benefits of working with a tree.

---

## Requirements

1. **Own mutable node model**
   - Node: type (module, class, function, block, statement, …), optional name, `parent`, `children`, source span (start_line, start_col, end_line, end_col), and either stored source fragment or generated text.
   - Replace subtree = swap the node (or its content) in parent’s `children`.
   - Insert/delete = modify the children list of the parent.

2. **Build from LibCST (one pass)**
   - Single walk over the LibCST tree.
   - For each node we care about (e.g. Module, ClassDef, FunctionDef, IndentedBlock, or statement-level nodes), create a corresponding mutable node, set parent/children and span (using PositionProvider).
   - Result: one mutable tree with correct up/down references and spans.

3. **Edits bottom-to-top**
   - Input: list of operations (node id or span → new code or subtree).
   - Sort operations by (end_line, end_col) descending.
   - For each: resolve the target node in **our** tree, replace its content (or subtree) in place; optionally update spans only along the changed branch.
   - No full-tree rebuild; only the affected path is touched.

4. **Back to LibCST / text**
   - **Option A:** Walk our tree and for each node output its source (stored or generated), concatenate to get the full file. Then pass the resulting string to LibCST once (parse for validation, or for further tree ops).
   - **Option B:** Build a new LibCST tree from our mutable tree and use LibCST for codegen/validation.

5. **Integration**
   - Current flow: `cst_load_file` → LibCST tree + node_map; `cst_modify_tree` uses LibCST replace/insert and hits the “stale node” issue in batch.
   - New flow for batch path: LibCST parse → build mutable tree; apply batch operations on mutable tree (bottom-to-top); serialize to source (or to LibCST); validate (e.g. compile); optionally update in-memory LibCST tree and node_map from the new source for subsequent commands.

---

## Out of scope (for this task)

- Replacing LibCST entirely for parsing/codegen.
- Changing the external API of `cst_modify_tree` (callers still pass operations; internally we may use the mutable layer when batch is detected or when requested).

---

## Deliverables

1. **Design doc** (this file or a separate design) describing the mutable node model, conversion LibCST → mutable, edit operations, and serialization.
2. **Implementation**
   - Module(s) under `code_analysis/core/` (e.g. `mutable_cst/` or `cst_mutable_layer/`) with:
     - Mutable node type(s) and tree structure.
     - Conversion: LibCST `Module` → mutable tree (using PositionProvider for spans).
     - Replace at node (by id or span), insert at position; both in place, with bottom-to-top ordering.
     - Serialization: mutable tree → source code (and optionally → LibCST tree).
   - Integration in the batch-modify path (e.g. in `tree_modifier` or command layer): when applying multiple replace/insert, build mutable tree once, apply all ops, serialize once, re-parse for validation and for further use.
3. **Tests**: batch replace (e.g. several methods in one class), batch insert; verify result parses and contains expected edits.

---

## Acceptance

- Batch of N replace operations (e.g. add docstrings to N methods in one class) succeeds in one call without “node not replaced” / “nodes were not inserted” errors.
- No regression for single-op replace/insert (existing behaviour preserved or explicitly routed through the same path).
- Resulting file is valid Python (e.g. compile) and contains all requested edits.
