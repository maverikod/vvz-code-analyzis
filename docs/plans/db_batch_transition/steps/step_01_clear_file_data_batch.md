# Step 01: clear_file_data — one execute_batch of DELETE ops

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../PLAN.md](../PLAN.md)  
**Parallel chains:** [../PARALLEL_CHAINS.md](../PARALLEL_CHAINS.md)  
**TZ:** [../TZ_DB_BATCH_TRANSITION.md](../TZ_DB_BATCH_TRANSITION.md)

---

## Executor role

Implementer: change only the function `clear_file_data` in the target file so that all DELETE operations (except those inside `_clear_file_vectors`) are executed via one call to `self.execute_batch(ops)` instead of multiple `self._execute(...)` calls. Optionally include the entity_cross_ref DELETE in the same batch by inlining the WHERE logic from `delete_entity_cross_ref_for_file`.

---

## Execution directive

- Execute only this step. Do not change step 02 or any other file.
- Read every file listed in "Read first" before writing code.
- Modify only `code_analysis/core/database/files/crud.py`; do not change `entity_cross_ref.py` or any other module.
- Do not add alternative logic (e.g. do not keep multiple _execute calls for the DELETEs that the TZ says to batch).
- Stop immediately if any blackstop is triggered.

---

## Step scope

- **Target code file:** `code_analysis/core/database/files/crud.py`
- **Step type:** Refactor existing function
- **Purpose:** Replace many `_execute("DELETE FROM ...")` in `clear_file_data` with one `execute_batch(ops)`.

---

## Dependency contract

- **Prerequisites:** None. This step is independent of step 02.
- **Unlocks:** Nothing else in this plan.
- **Forbidden scope:** Do not modify `_clear_file_vectors`, `delete_entity_cross_ref_for_file` definitions; only change how `clear_file_data` uses them or replaces the call to `delete_entity_cross_ref_for_file` with one batch op.

---

## Required context

- `self` in `clear_file_data` is the database instance (CodeDatabase-like) and has `execute_batch(operations: List[Tuple[str, Optional[tuple]]], transaction_id=None)` and `_commit()`. See `code_analysis/core/database/base.py` for `execute_batch` signature.
- Current flow: `_clear_file_vectors(file_id)` then SELECTs for class_ids and content_ids, then `delete_entity_cross_ref_for_file(file_id)`, then conditional DELETE code_content_fts, conditional DELETE methods, then DELETE classes, functions, imports, issues, usages, code_content, ast_trees, cst_trees, then `_commit()`.
- Target flow: `_clear_file_vectors(file_id)` unchanged. Then gather all IDs needed for the batch (class_ids, method_ids for those classes, function_ids, content_ids) via the same SELECTs as today (and as in `delete_entity_cross_ref_for_file` for method_ids/function_ids if inlining). Build a list `ops` of `(sql, params)` tuples in the exact order given in "Expected file change". Call `self.execute_batch(ops)`. Call `self._commit()`.

---

## Read first

- `docs/plans/db_batch_transition/TZ_DB_BATCH_TRANSITION.md` (sections 1, 3, 4, 6)
- `docs/reports/DB_TABLES_AND_BATCH_AUDIT.md` (section 2.4 and Summary row "Clear/delete")
- `code_analysis/core/database/files/crud.py` (function `clear_file_data`, and `_clear_file_vectors` for context)
- `code_analysis/core/database/entity_cross_ref.py` (function `delete_entity_cross_ref_for_file` and the construction of `where_clause` and `params` for `DELETE FROM entity_cross_ref WHERE ...`)
- `code_analysis/core/database/base.py` (method `execute_batch` signature and docstring)

---

## Expected file change

- In `clear_file_data(self, file_id: int)`:
  1. Keep the first line: `self._clear_file_vectors(file_id)`.
  2. Keep the same SELECTs to obtain: `class_ids` (from classes WHERE file_id = ?), and for inlining entity_cross_ref: `method_ids` (SELECT id FROM methods WHERE class_id IN (...)), `function_ids` (SELECT id FROM functions WHERE file_id = ?). Also `content_ids` (SELECT id FROM code_content WHERE file_id = ?).
  3. Build a list `ops` of tuples `(sql_string, params_tuple)` in this exact order:
     - One DELETE for entity_cross_ref: same WHERE logic as in `delete_entity_cross_ref_for_file` (conditions: file_id = ?; if class_ids add caller_class_id IN (...), callee_class_id IN (...); if method_ids add caller_method_id IN (...), callee_method_id IN (...); if function_ids add caller_function_id IN (...), callee_function_id IN (...)). Single SQL with " OR ".join(conditions) and params list [file_id, ...class_ids, ...class_ids, ...method_ids, ...method_ids, ...function_ids, ...function_ids]. Append `("DELETE FROM entity_cross_ref WHERE " + where_clause, tuple(params))`.
     - If content_ids is non-empty: one DELETE FROM code_content_fts WHERE rowid IN (placeholders) with tuple(content_ids).
     - If class_ids is non-empty: one DELETE FROM methods WHERE class_id IN (placeholders) with tuple(class_ids).
     - One DELETE FROM classes WHERE file_id = ? with (file_id,).
     - One DELETE FROM functions WHERE file_id = ? with (file_id,).
     - One DELETE FROM imports WHERE file_id = ? with (file_id,).
     - One DELETE FROM issues WHERE file_id = ? with (file_id,).
     - One DELETE FROM usages WHERE file_id = ? with (file_id,).
     - One DELETE FROM code_content WHERE file_id = ? with (file_id,).
     - One DELETE FROM ast_trees WHERE file_id = ? with (file_id,).
     - One DELETE FROM cst_trees WHERE file_id = ? with (file_id,).
  4. Call `self.execute_batch(ops)` (no transaction_id required for this use).
  5. Call `self._commit()`.
  6. Remove the call to `self.delete_entity_cross_ref_for_file(file_id)` and remove all the remaining `_execute` and conditional `_execute` calls that are replaced by the batch. The function must not call `_execute` for any of the DELETE statements that are now in `ops`.

---

## Forbidden alternatives

- Do not leave any of the DELETEs (entity_cross_ref, code_content_fts, methods, classes, functions, imports, issues, usages, code_content, ast_trees, cst_trees) as separate `_execute` calls.
- Do not change the behaviour of `_clear_file_vectors` or call it at a different time.
- Do not add a new helper in another file; all logic stays in crud.py for this step.
- Do not use a transaction_id for execute_batch unless the existing codebase already uses one in similar contexts in this file.

---

## Atomic operations

1. In `clear_file_data`, after `_clear_file_vectors(file_id)`, collect class_ids, method_ids, function_ids, content_ids with the same SELECTs as in current code and in entity_cross_ref (for method_ids/function_ids).
2. Build the entity_cross_ref WHERE and params exactly as in `delete_entity_cross_ref_for_file`.
3. Build list `ops` in the exact order: entity_cross_ref DELETE, then code_content_fts (if content_ids), then methods (if class_ids), then classes, functions, imports, issues, usages, code_content, ast_trees, cst_trees.
4. Replace the block from `delete_entity_cross_ref_for_file` through the last `_execute` and `_commit()` with `self.execute_batch(ops)` and `self._commit()`.
5. Ensure no remaining _execute for those DELETEs.

---

## Expected deliverables

- `clear_file_data` still clears all data for the file (vectors, entity_cross_ref, code_content_fts, methods, classes, functions, imports, issues, usages, code_content, ast_trees, cst_trees) with identical semantics.
- All those DELETEs (except what is inside `_clear_file_vectors`) are executed via a single `execute_batch(ops)`.
- File passes black, flake8, mypy; full test suite passes.

---

## Mandatory validation

- All commands from project root.
- Run `black code_analysis/core/database/files/crud.py` — no formatting changes left.
- Run `flake8 code_analysis/core/database/files/crud.py` — zero violations.
- Run `mypy code_analysis/core/database/files/crud.py` — zero type errors.
- Run `pytest` from project root — all tests must pass. Step is not complete until the test suite is green.

---

## Decision rules

- If the target file would exceed 350–400 lines after the change, do not split in this step; the refactor should not add much length.
- For building the entity_cross_ref WHERE: use the same condition list and param order as in `entity_cross_ref.delete_entity_cross_ref_for_file` (file_id = ?; then class_ids for caller_class_id and callee_class_id; then method_ids for caller_method_id and callee_method_id; then function_ids for caller_function_id and callee_function_id). Use " OR ".join(conditions) and a single tuple of params.
- If content_ids is empty, do not add any op for code_content_fts. If class_ids is empty, do not add any op for methods (but still add DELETE FROM classes with file_id = ?).

---

## Blackstops

- Stop if you must change any file other than `code_analysis/core/database/files/crud.py`.
- Stop if `clear_file_data` would still call `_execute` for any of the DELETEs that are to be batched (entity_cross_ref, code_content_fts, methods, classes, functions, imports, issues, usages, code_content, ast_trees, cst_trees).
- Stop if the order of ops differs from the specified order (entity_cross_ref first, then code_content_fts, methods, classes, functions, imports, issues, usages, code_content, ast_trees, cst_trees).

---

## Handoff package

Return: path of modified file; confirmation that "Read first" files were read; confirmation that all DELETEs in the batch are in the specified order and that `execute_batch(ops)` and `_commit()` are used; validation evidence (black, flake8, mypy, pytest); any blockers or risks.
