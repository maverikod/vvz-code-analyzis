# Step 6: Optional apply + save in one request (batch + file); save failure = nothing changed

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Plan index:** [REFACTOR_PLAN.md](../REFACTOR_PLAN.md)

---

## Goal

Allow one request to apply a batch of operations and save the tree to a file (project_id + file_path). If **save fails**, nothing must change (file, database); the tool returns a **clear error description** for the model. Optionally roll back the in-memory tree so the model can retry the same request.

## File to modify

`code_analysis/commands/cst_modify_tree_command.py` (single primary file: extend modify command, not save command)

## Behaviour

- Add optional parameters e.g. `project_id`, `file_path` (and optionally `backup`, `validate`, `commit_message`). When both present: after applying all operations, call the same logic as cst_save_tree (or invoke save internally) and return both modify result and save result (e.g. file_path, backup_uuid).
- **If modify fails:** do not save; tree unchanged; return error with a **clear description and cause** of the failure so the model can fix and retry.
- **If save fails:**
  - **Nothing must change:** file on disk unchanged, database unchanged. No partial write, no DB update (write is rolled back to the previous state).
  - **Error for the model:** The tool must return a **clear, model-friendly error description and the cause of the failure** (e.g. validation error, write error, path error, underlying exception message) so the model can understand why it failed and retry after fixing.
  - **In-memory tree:** On save failure, **roll back** the in-memory tree on the server to the state **before** the batch was applied. Thus: no change to file, DB, or server tree.
  - **Model context:** The model keeps in memory the batch it sent; it does not need to re-obtain it. Only the file and database are reverted; the model can retry the same request (same tree_id, same operations) after fixing the cause.
- Response when save fails: e.g. `modify_applied: false` (because rolled back), `save_applied: false`, `save_error: "<clear description>"`, and **cause/reason of the failure** (so the model receives both what happened and why). Document that the client may retry the same batch after fixing the cause.

## References

- Concept §6.3a “optionally the same batch can be passed together with file”; §6.4 “Save fails — nothing must change”: [CST_CONCEPT_AND_PIPELINE.md](../CST_CONCEPT_AND_PIPELINE.md)

## Success metrics

- Request with tree_id, operations, project_id, file_path: operations applied and file written; response includes save outcome.
- Request with tree_id, operations only: current behaviour (no save).
- Modify failure: no save, tree unchanged.
- Save failure: file unchanged, DB unchanged, in-memory tree rolled back; response includes clear `save_error` and cause/reason of the failure; model can retry same request after fix.

## Post-step checks

- Search and fix: incomplete code, TODO, ellipsis/syntax violations, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations from project/plan rules.
- Run `code_mapper -r <project_code_dir>` and fix all reported errors.
- Run `mypy`, `flake8`, `black` and fix all reported issues.
