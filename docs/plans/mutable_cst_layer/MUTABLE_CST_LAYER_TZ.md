# Technical specification (TZ): Mutable CST layer for batch edits

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Purpose:** Handoff-ready specification for the implementing model. Execute as stated; no API change for callers. The mutable layer must apply to **all** CST code paths that **call modify_tree** (see section 3.5).

**Source task:** [MUTABLE_CST_LAYER_TASK.md](../MUTABLE_CST_LAYER_TASK.md)

**Plan:** [PLAN.md](PLAN.md) — step-by-step implementation (1 code file = 1 step).

---

## 1. Role of the executor

- **You are the implementing model.** You write production code and tests in this repository only.
- **Do not change** the external API of `cst_modify_tree` (parameters, response shape, command name). Callers continue to pass `tree_id` and `operations`; internally the batch path may use the mutable layer.
- **Do not remove** existing behaviour: single-op replace/insert/delete must remain working (same or explicitly routed path). No regression.
- **Code and docstrings:** English only. File/class/method docstrings must include: `Author: Vasiliy Zdanovskiy`, `email: vasilyvz@gmail.com`.
- **No:** hardcode, placeholders, backward-compatibility or fallback logic unless this TZ explicitly requires it. No TODO, no `NotImplemented` outside abstract methods, no `pass` outside exception bodies. No file over 350–400 lines; one class per file (except small enums/exceptions). After each file: run black, flake8, mypy and fix all issues; run code_mapper after each batch of changes.

---

## 2. Goal (summary)

Introduce a **mutable tree layer** between LibCST and edit operations: LibCST parses once → we build one mutable tree → apply all replace/insert/delete **in place, bottom-to-top** → serialize to source (or build LibCST tree) once → validate and optionally re-index for further commands. This fixes batch edit failures caused by LibCST’s immutability (stale `node_map` after the first replace).

---

## 3. Deliverables (what you must implement)

### 3.1 Design document

- **Location:** Either extend `docs/plans/MUTABLE_CST_LAYER_TASK.md` or add `docs/plans/design/MUTABLE_CST_LAYER_DESIGN.md` (if you create a new file, ensure `docs/plans/design/` exists and is allowed by project rules).
- **Content (English):** Describe in prose and/or short schemas:
  - Mutable node model: type, optional name, `parent`, `children`, source span (`start_line`, `start_col`, `end_line`, `end_col`), and either stored source fragment or generated text.
  - Conversion: LibCST `Module` → mutable tree in one pass using `PositionProvider` for spans; which LibCST node types are mapped (e.g. Module, ClassDef, FunctionDef, IndentedBlock, statement-level nodes).
  - Edit operations: replace at node (by id or span), insert at position; both in place; ordering: by `(end_line, end_col)` descending.
  - Serialization: mutable tree → full source code string; optionally mutable tree → LibCST `Module`.
- No code in the design doc; only description.

### 3.2 Implementation (code)

- **Place:** New package under `code_analysis/core/`. Name the package either `mutable_cst` or `cst_mutable_layer` (one of them; keep naming consistent).
- **Layout (obey one class per file, max ~350–400 lines):**
  - **Mutable node model:** A dataclass (or small class hierarchy) for a single mutable node: type (e.g. module, class, function, block, statement), optional name, `parent` reference, `children` list, span (`start_line`, `start_col`, `end_line`, `end_col`), and either stored source text or a way to generate text. Node identity: use a stable id (e.g. UUID) per node for "replace by id" and "insert at parent".
  - **Tree type:** A root mutable node (or a thin wrapper) holding the whole tree and a map from node id → mutable node for resolution.
  - **Build from LibCST:** One function (or small module): single walk over a LibCST `Module` (using `MetadataWrapper` + `PositionProvider`); for each relevant node type create a mutable node, set parent/children and span; result is one mutable tree with correct up/down references and spans. Reuse or mirror the set of node types currently indexed in `tree_builder._build_tree_index` where it makes sense (Module, ClassDef, FunctionDef, IndentedBlock, statement-level).
  - **Edits:**
    - **Replace:** By node id (or by span): resolve the mutable node, replace its content (or swap the node in parent's `children`); do not rebuild the whole tree.
    - **Insert:** By parent id and position (e.g. first/last/after index): modify parent's `children` in place.
    - **Delete:** Remove node from parent's `children` in place.
  - **Ordering:** Input list of operations must be sorted by (end_line, end_col) descending before applying; apply in that order so earlier positions are not invalidated.
  - **Serialization:**
    - **To source:** Walk the mutable tree and output each node's source (stored or generated), concatenating to form the full file string.
    - **Optional:** Function to build a LibCST `Module` from the mutable tree (for validation/codegen if needed).
  - **Parsing new code:** Reuse existing `tree_modifier_ops.parse_code_snippet` and `parse_code_snippet_or_comment` for turning replacement/insert code strings into statements. When to use which: follow current usage in `tree_modifier_ops` (replace → `parse_code_snippet`; insert where comment-only lines are allowed → `parse_code_snippet_or_comment`). The mutable layer then stores or attaches the corresponding source text for the new nodes.
- **Dependencies:** Use only project-approved dependencies; LibCST and `libcst.metadata.PositionProvider` are already used in `code_analysis/core/cst_tree/`.
- **Imports:** Only at top of file; no circular imports. New package must not import from the command layer; the command/tree_modifier layer imports from the new package.

### 3.3 Integration with current flow

- **Single implementation point:** All changes are made inside `code_analysis.core.cst_tree.tree_modifier.modify_tree(tree_id, operations)` (and code it calls). **Every** caller of `modify_tree` (see section 3.5) then automatically uses the mutable layer for batch edits; no changes to command or RPC code are required.
- **Entry point:** `code_analysis.core.cst_tree.tree_modifier.modify_tree(tree_id, operations)`.
- **Current behaviour:** Builds `CSTTree` from `get_tree(tree_id)`; validates all operations; sorts operations; applies each op via `_apply_operation` (which uses `tree_modifier_ops.replace_node`, `delete_node`, `insert_node_*`, etc.) on a copy of `tree.module`; after each op assigns `tree.module = modified_module` and cleans index for affected nodes; after all ops rebuilds full index via `_build_tree_index`; validates module by compile.
- **Required change:** When a **batch** of replace/insert/delete is detected (e.g. more than one replace, or more than one insert, or any delete in the same call), use the mutable layer instead of the current LibCST-in-place path:
  1. Get `tree = get_tree(tree_id)` (existing).
  2. Validate all operations (existing validation logic; validation may need to run on the current tree's index so node_ids exist; keep validation in `tree_modifier_validate` or equivalent).
  3. Build **one** mutable tree from `tree.module` (LibCST → mutable conversion).
  4. Map existing `node_id` (UUID from `tree.metadata_map`) to mutable node id: the mutable tree must be built so that the same UUIDs from the current `tree.metadata_map` are used as node identifiers in the mutable tree (so operations that reference `node_id` still resolve). This implies that when building the mutable tree from LibCST, you assign each mutable node the same id that the current index has for that LibCST node (positions + type).
  5. Sort operations by (end_line, end_col) descending (use metadata from `tree.metadata_map` for line/col).
  6. Apply all operations on the mutable tree (replace/insert/delete in place).
  7. Serialize mutable tree → source code string.
  8. Parse the string with LibCST to get new `cst.Module`; run `compile(module.code, "<string>", "exec")` for validation.
  9. Update `tree.module` with the new module; clear and rebuild `tree.node_map`, `tree.metadata_map`, `tree.parent_map` via existing `_build_tree_index` so that subsequent commands see the new tree.
- **Single-op or non-batch:** Either keep the current code path unchanged for a single replace/insert/delete, or route through the mutable layer as well; in either case, behaviour must remain the same and no regression.
- **Replace_range and MOVE:** Either implement them in the mutable layer (preferred) or keep calling the current LibCST path for those op types only; the TZ does not require removing the current path for REPLACE_RANGE/MOVE if you defer them, but batch replace/insert/delete must use the mutable layer so that e.g. "add docstrings to N methods" succeeds in one call.

### 3.4 Tests

- **Location:** `tests/`.
- **New test file(s):** e.g. `tests/test_mutable_cst_layer.py` and/or extend `tests/test_tree_modifier.py`. Prefer a dedicated test file for the mutable layer (unit tests for build, replace, insert, delete, serialize) and integration tests that call `modify_tree` with multiple operations.
- **Required scenarios:**
  - **Batch replace:** One class with several methods; one `modify_tree` call with multiple replace operations (e.g. add or change docstrings for several methods). Assert: no "node not replaced" / "nodes were not inserted" errors; result compiles; all requested edits are present in the file.
  - **Batch insert:** e.g. insert several statements or blocks in one call. Assert: all inserts applied; result compiles.
  - **No regression:** Existing tests in `tests/test_tree_modifier.py` must pass (single replace, single insert, delete, replace_range if covered).
- Use `create_tree_from_code` and `modify_tree` from the existing API; assert on `modified.module.code` and `compile(...)`.

### 3.5 All CST entry points that modify the tree (scope of the mechanism)

The mutable layer must effectively apply to **all** commands and flows that modify the CST tree. Analysis of the codebase:

| Entry point | Module / flow | Calls `modify_tree`? | Covered by mutable layer? |
|-------------|----------------|----------------------|----------------------------|
| **cst_modify_tree** (MCP command) | `commands/cst_modify_tree_command.py` | Yes | Yes — integration in `modify_tree` covers it. |
| **compose_cst_module** (tree_id + node_id) | `commands/compose_cst_tree_flow.py` | Yes (`modify_tree(file_tree_id, operations)`) | Yes — same `modify_tree` path. |
| **modify_cst** (RPC) | `database_driver_pkg/rpc_handlers_cst_modify.py` | Yes (`modify_tree(tree.tree_id, operations)`) | Yes — same path. |
| **AST modify** (RPC) | `database_driver_pkg/rpc_handlers_ast_modify.py` | Yes (`modify_tree(tree.tree_id, operations)`) | Yes — same path. |
| **compose_cst_module** (ops only) | `commands/compose_cst_ops_flow.py` → `core/cst_module/patcher.apply_replace_ops` | No | Different path: works on **source string** and applies all replacements in **one** LibCST transformer visit (position-keyed dict). Does not use an in-memory tree or `modify_tree`; does not suffer from the "stale node" batch bug. **Out of scope** for this TZ: no change to patcher. Optional future work: unify all CST edits via the mutable layer (e.g. compose_cst ops → parse → mutable tree → apply → serialize). |

**Requirement:** Implement the mutable layer only in `tree_modifier.modify_tree` (batch path). All four entry points that call `modify_tree` then automatically use it; no edits to `cst_modify_tree_command.py`, `compose_cst_tree_flow.py`, `rpc_handlers_cst_modify.py`, or `rpc_handlers_ast_modify.py` are required.

---

## 4. Out of scope (do not do)

- Replacing LibCST entirely for parsing or codegen.
- Changing the external API of `cst_modify_tree` (parameters or return structure).
- Adding backward-compatibility or fallback logic beyond what is needed to preserve single-op behaviour.
- Changing `compose_cst_module` ops flow or `core/cst_module/patcher.py` (apply_replace_ops). The mechanism applies to all paths that **call modify_tree**; the ops flow does not call it.

---

## 5. Acceptance criteria (obligatory)

- A batch of N replace operations (e.g. add docstrings to N methods in one class) succeeds in one `modify_tree` call without "node not replaced" / "nodes were not inserted" errors.
- No regression for single replace, single insert, delete (existing tests pass).
- The resulting file is valid Python (e.g. `compile(module.code, "<string>", "exec")` succeeds) and contains all requested edits.
- All new code: black, flake8, mypy clean; file size and structure per project rules; docstrings with Author/email.

---

## 6. Blackstops (mandatory checkpoints)

1. **After implementing the mutable node model and tree build:** Run black, flake8, mypy on the new files; fix all issues. Run code_mapper.
2. **After implementing replace/insert/delete and serialization:** Run black, flake8, mypy; run code_mapper.
3. **After integration in `tree_modifier`:** Run full test suite for `tests/test_tree_modifier.py` and new mutable-layer tests; fix any failure.
4. **Final:** Run all tests that touch CST/tree modifier; run black, flake8, mypy on changed and new files; re-read this TZ and confirm every requirement is met and no forbidden item (hardcode, TODO, etc.) remains.

---

## 7. Re-check and fix (mandatory)

After writing all code:

- Re-run the full subset of tests related to tree modification and mutable layer.
- Re-run black, flake8, mypy on every touched file.
- Verify acceptance criteria in section 5 one by one.
- If any acceptance fails or any checkpoint fails, fix before considering the task complete.

---

## 8. References (code locations)

- Task and context: `docs/plans/MUTABLE_CST_LAYER_TASK.md`
- Current modifier: `code_analysis/core/cst_tree/tree_modifier.py` — `modify_tree`, `_apply_operation`, `_sort_operations_for_batch`
- Current ops: `code_analysis/core/cst_tree/tree_modifier_ops.py` — `replace_node`, `delete_node`, `insert_node_at_position`, `insert_node_relative`, `find_node_in_module_by_position`, `PositionProvider`
- Tree model: `code_analysis/core/cst_tree/models.py` — `CSTTree`, `TreeOperation`, `TreeNodeMetadata`, `ROOT_NODE_ID_SENTINEL`
- Tree index build: `code_analysis/core/cst_tree/tree_builder.py` — `_build_tree_index`, `load_file_to_tree`, `create_tree_from_code`, `get_tree`
- Validation: `code_analysis/core/cst_tree/tree_modifier_validate.py` — `_validate_operation`
- Callers of `modify_tree` (do not change their API or call pattern): `code_analysis/commands/cst_modify_tree_command.py`, `code_analysis/commands/compose_cst_tree_flow.py`, `code_analysis/core/database_driver_pkg/rpc_handlers_cst_modify.py`, `code_analysis/core/database_driver_pkg/rpc_handlers_ast_modify.py`
- compose_cst_module ops path (out of scope): `code_analysis/core/cst_module/patcher.py` — `apply_replace_ops`, `_StatementListRewriter`; `code_analysis/commands/compose_cst_ops_flow.py` — `run_ops_mode`
- Existing tests: `tests/test_tree_modifier.py`

---

## 9. Summary checklist for executor

- [ ] Design doc written (extend MUTABLE_CST_LAYER_TASK.md or new file in docs/).
- [ ] Package under `code_analysis/core/` (mutable_cst or cst_mutable_layer): mutable node, tree, build from LibCST, replace/insert/delete in place, sort by (end_line, end_col) desc, serialize to source (and optionally to LibCST).
- [ ] Integration: in `modify_tree`, batch path builds mutable tree once, applies all ops, serializes once, re-parses and updates `tree.module` and index; single-op path unchanged or same result. All four callers of `modify_tree` (cst_modify_tree, compose_cst_tree_flow, rpc_handlers_cst_modify, rpc_handlers_ast_modify) automatically use this; no changes to those files.
- [ ] Tests: batch replace (e.g. N methods), batch insert; no regression for existing test_tree_modifier tests.
- [ ] No API change for any command or RPC; no hardcode/TODO/NotImplemented/pass (except as allowed); file size and docstrings per project rules.
- [ ] All blackstops and re-check performed.
