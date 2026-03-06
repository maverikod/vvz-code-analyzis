"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Technical Assignment: File-as-Source-of-Truth and Unified File-Level DB Write Pipeline

## 1. Objective

Implement a unified architecture where:

1. The **file on disk is the source of truth** in all collision scenarios.
2. **Tree-to-DB write from tool flow** and **background indexing flow** call the **same implementation path**.
3. The **minimal write unit is one file** (file-level atomic write semantics).
4. Database stores tree data in a form that allows **full file restoration** (not only node metadata, ranges, names, IDs).

## 2. Scope

This assignment covers:

- CST save flow (`cst_save_tree` and related save helpers).
- Background indexing flow (index worker / update indexes path).
- File restoration from DB (`db -> file`).
- DB synchronization from file (`file -> db`).
- Related tests for invariants, atomicity, and restoration fidelity.

## 3. Core Invariants (Mandatory)

1. **Single write implementation path** for:
   - Tree-based write via tool.
   - Background indexing of existing files.
2. **File-level atomicity**:
   - A file DB write is either fully completed for that file or considered failed.
   - No "partially updated file index" success state.
3. **Source of truth = file**:
   - If file exists, DB is synchronized from file content.
   - DB content must not overwrite existing file unless explicit `force` recovery operation is requested.
4. **Full restoration capability**:
   - DB must retain complete tree/source representation needed to reconstruct file text fully.
   - Node metadata only is not sufficient.

## 4. Data Requirements

For each indexed/saved file, DB must store:

- Complete CST/source payload sufficient for full text reconstruction.
- File linkage (`file_id`, `project_id`, absolute normalized path relation via files table).
- Timestamp metadata used for operational decisions.
- Full node ordering semantics (parent-child relations and sibling order).

Important:

- `node_id`, range offsets, entity names, and file references are auxiliary metadata.
- They cannot be the sole restoration basis.

## 4.1 Mandatory Content Fidelity

The stored tree/source representation must preserve all semantically relevant and text-relevant content:

1. **All data types** used in code must remain representable and restorable:
   - numbers, strings, bytes, booleans, `None`,
   - collections (list/tuple/set/dict),
   - literals and annotations.
2. **Docstrings** must be preserved as-is.
3. **Comments** must be preserved when parser/model supports them.

Implementation rule:

- For CST pipeline (LibCST), comments are expected to be preserved natively.
- Do not transform comments to docstrings in normal mode.

Exceptional fallback rule (allowed only if a concrete technical limitation is proven):

1. Temporary `comment -> docstring` transform before parser handoff.
2. Mandatory reverse transform after write-back to file.
3. Mandatory round-trip tests proving no permanent semantic/text loss.
4. Mandatory explicit documentation of this mode in implementation report.

## 5. Unified Pipeline Requirement

Introduce or finalize one shared service function (name can differ, behavior is fixed), e.g.:

- `sync_file_to_db_atomic(...)`

Required behavior:

1. Input is file-centric (project, absolute file path, source code, mtime/context).
2. Rebuilds and writes all file-level DB structures in one coordinated operation.
3. Used by both:
   - Tree save command flow.
   - Background indexing flow.
4. Returns structured result:
   - `success`
   - `file_id`
   - counters for written structures
   - `error` on failure

## 6. Write Unit and Atomicity Semantics

Minimal write unit is **one file**:

- All DB structures for a file are updated as one unit.
- If any stage fails, operation result is failure for that file.
- Caller must not report the file as successfully indexed/saved.

Note:

- This requirement is file-level atomicity and consistency semantics.
- Internal implementation may use transaction/batch mechanics, but external behavior must satisfy full-file success/failure contract.

Sibling order is mandatory:

- Persist child order per parent (e.g. `child_index`).
- Enforce unique order slot per parent.
- Reconstruction must order children strictly by stored sibling order.

## 7. Collision Policy

Policy is intentionally simple:

1. If file exists on disk, file content is canonical.
2. DB is updated from file.
3. DB-to-file overwrite is blocked by default when file exists.
4. Explicit restore operation may allow overwrite only with:
   - `force=true`
   - mandatory backup before overwrite.

## 8. Restoration Requirements

Implement/standardize two explicit operations:

1. **Restore file from DB** (`db -> file`)
   - Uses full stored CST/source payload.
   - Supports safe mode (no overwrite when target exists).
   - Supports forced mode (`force=true`) with mandatory backup.

2. **Sync DB from file** (`file -> db`)
   - Uses the same unified file pipeline as all other write flows.

Acceptance for restoration fidelity:

- Restored file content must match original indexed text fully (subject only to explicitly documented and accepted normalization policy, if any).

## 9. Prohibited Patterns

1. Separate independent write logic for tree-save and indexing flows.
2. Partial file DB success states.
3. DB as default collision winner over existing file.
4. Restoration based only on node metadata without complete source/tree payload.
5. New compatibility/fallback branches unless explicitly requested.

## 10. Required Tests

### 10.1 Unified code path tests

1. Tree save flow calls the unified file sync function.
2. Background indexing flow calls the same unified function.
3. No bypass path for these two flows (verified by spy/patch assertions).

### 10.2 File-level write unit tests

4. Inject failure during file DB sync; operation must fail for that file.
5. File must not be reported as successfully indexed/saved in failure case.
6. Re-run after failure restores consistent full-file state.

### 10.3 Restoration tests

7. `file missing + DB source exists` -> full restore succeeds.
8. `file exists + force=false` -> safe refusal (no overwrite).
9. `file exists + force=true` -> overwrite succeeds with backup.
10. Fidelity test: index -> delete -> restore -> compare full text equality.
11. Sibling order round-trip test: save/load/reconstruct preserves child order exactly.
12. Comment/docstring fidelity test: comments and docstrings survive round-trip unchanged.
13. Data-type fidelity test: literals and container forms are preserved across round-trip.

## 11. Acceptance Criteria

Implementation is accepted only if all are true:

1. Single shared file sync implementation is used by both required flows.
2. Minimal write unit behavior is file-level success/failure.
3. File remains source-of-truth in collisions.
4. Full file restoration from DB is proven by tests.
5. All updated and new tests pass.
6. `black`, `flake8`, and `mypy` pass without unresolved issues.

## 12. Blackstops (Mandatory Stop Conditions)

Stop and escalate immediately if:

1. Existing transaction/driver behavior prevents guaranteed file-level consistency contract.
2. Single unified path cannot be wired without breaking required public behavior.
3. Data model cannot guarantee full restore payload persistence for all write flows.
4. Hidden legacy path still writes file structures outside the unified pipeline.

## 13. Implementation Report Format (Mandatory)

Final executor report must include:

1. List of modified files.
2. Unified call flow diagram in text form.
3. Removed/bypassed duplicate paths.
4. Test evidence for each mandatory test category.
5. Quality checks output summary (`black`, `flake8`, `mypy`).
6. Residual risks (if any).

