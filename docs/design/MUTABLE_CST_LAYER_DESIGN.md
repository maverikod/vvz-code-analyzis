# Design: Mutable CST layer for batch edits

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Context:** [MUTABLE_CST_LAYER_TZ.md](../mutable_cst_layer/MUTABLE_CST_LAYER_TZ.md), [PLAN.md](../mutable_cst_layer/PLAN.md). This document describes the mutable node model, conversion, edits, and serialization in prose only (no implementation code).

---

## 1. Mutable node model

- **Node type:** A single mutable node is a record with:
  - **node_id:** Stable identifier (UUID string), same as used in the existing tree index (`metadata_map`), so operations that reference `node_id` resolve.
  - **type:** LibCST node type name (e.g. `Module`, `ClassDef`, `FunctionDef`, `IndentedBlock`, statement types).
  - **name:** Optional (e.g. class/function name); used for display and debugging.
  - **parent:** Reference to the parent mutable node (or `None` for root).
  - **children:** Ordered list of child mutable nodes (in source order).
  - **span:** `start_line`, `start_col`, `end_line`, `end_col` (1-based line, 0-based column).
  - **source:** The full source text fragment for this node (e.g. for a `FunctionDef`, the entire `def name(...): ...` block). This is either stored when building from LibCST or set when applying replace/insert.

- **Tree type:** A thin wrapper (e.g. root node plus a map) that holds:
  - The root mutable node (type `Module`).
  - A map `node_id → mutable node` for O(1) resolution of operations by `node_id`.

- **Identity:** Node identity is the stable `node_id`. When building from LibCST, each mutable node receives the same `node_id` as in the existing `metadata_map` for the corresponding LibCST node (see Conversion below).

---

## 2. Conversion (LibCST → mutable tree)

- **Input:** A LibCST `Module` and the current `metadata_map` (node_id → TreeNodeMetadata) from the existing tree.
- **Process:** Single walk over the LibCST tree using `MetadataWrapper` and `PositionProvider`. For each node that is indexed in the existing tree (same set as in `tree_builder._build_tree_index`: all nodes that get a position, i.e. no filter by default):
  - Resolve position (start/end line and column).
  - Resolve `node_id`: match current node to `metadata_map` by `(start_line, start_col, end_line, end_col, type)` so the same UUID is used; if no match, assign a new UUID (should not happen when building from an already-indexed tree).
  - Get source fragment: `module.code_for_node(node)` (or equivalent) for the LibCST node in the context of the module.
  - Create a mutable node with that `node_id`, type, name (if any), span, source, and empty `children`; register in the tree’s node map.
  - Set parent/children: during the walk, maintain parent stack and attach each node to its parent’s `children` list in order.
- **Output:** One mutable tree (root + node map) with correct up/down references, spans, and source text. Every key in the input `metadata_map` must appear in the tree’s node map and point to a node with matching span and type.

---

## 3. Edit operations

- **Replace (by node_id):** Resolve the mutable node in the tree’s map. Parse the new code with the same rules as the current modifier (e.g. `parse_code_snippet` for replace). Set the node’s `source` to the string form of the parsed result (or the normalized code). Do not rebuild the whole tree; only update that node’s content. If the operation semantics require “swap in parent’s children”, the same node can be kept and only its `source` updated; serialization will emit the new source.

- **Insert (by parent_node_id and position):** Resolve the parent mutable node. Parse the new code with `parse_code_snippet_or_comment` (so comment-only lines are allowed). Create one or more mutable nodes for the parsed statements (or use a single “block” node that stores the concatenated source). Insert them into the parent’s `children` at the requested position (first / last / after index). Assign new UUIDs to inserted nodes. Register them in the tree’s node map. Update parent’s `children` in place.

- **Delete:** Resolve the mutable node by `node_id`. Remove it from the parent’s `children` list in place. Remove it from the tree’s node map. No full-tree rebuild.

- **Ordering:** The list of operations must be applied in order sorted by `(end_line, end_col)` descending (bottom-to-top). So the caller (or the edit module) sorts before applying; each operation is applied in place on the mutable tree. This avoids position shift invalidating later operations.

---

## 4. Serialization

- **To source:** Walk the mutable tree in document order (e.g. pre-order or a walk that respects the root’s `children` order). For the root (Module), output the concatenation of each child’s `source` with appropriate newlines (e.g. `"\n".join(child.source for child in root.children)`). No need to output a “header” for the module itself. The result is the full file source string.

- **Optional — to LibCST:** If required for validation or codegen, provide a function that builds a LibCST `Module` from the mutable tree (e.g. parse the serialized source string with `cst.parse_module`, or build nodes programmatically). The primary path is mutable tree → source string → parse once for validation and for updating the in-memory tree.

---

## 5. Integration point

- All batch replace/insert/delete flows go through `tree_modifier.modify_tree`. When a batch is detected (e.g. more than one replace, or more than one insert, or any delete in the same call), the modifier: gets the tree, validates operations, builds one mutable tree from `tree.module` and current `metadata_map`, sorts operations by (end_line, end_col) descending, applies all operations on the mutable tree, serializes to source, parses with LibCST, validates with `compile`, then updates `tree.module` and rebuilds the index via `_build_tree_index`. Single-op path can remain as is or use the same mutable path; REPLACE_RANGE/MOVE can stay on the current LibCST path or be implemented in the mutable layer later.
