# Implementation Plan: File Source of Truth and Full Tree Storage

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Role of execution model

**Role:** Senior Python developer and integrator.  
Implement exactly this plan and TZ with no scope creep.

---

## Canonical validation metrics

### Valid code metrics

- Fully comply with project and user rules.
- No hardcode, placeholders, compatibility fallbacks unless explicitly requested.
- No incomplete code: no TODO/FIXME, no `NotImplemented` outside abstract methods, no `pass` outside exception bodies.
- No deviation from task scope.

### Valid task metrics (for each step)

- Exact role is defined.
- Internal consistency.
- Completeness and precision.
- Consistency with project rules.
- 100% handoff readiness.
- Mandatory blackstops.
- Mandatory re-check and fixes after coding.

### Valid plan metrics

- Steps are split into separate files under `../steps/`.
- **1 step = 1 code file = 1 step description file**.
- Step sequence respects dependencies.
- Each step is self-sufficient via links and context.
- Parallel execution chains are described in a separate file.

---

## Mandatory checks after each code step

1. Re-read the step file and verify all outputs are implemented exactly.
2. Run and fix:
   - `code_mapper -r code_analysis`
   - `black <touched_file>`
   - `flake8 <touched_file>`
   - `mypy <touched_file>`
3. Run step-specific behavior checks and fix regressions.
4. Confirm no violations of valid code metrics.

---

## Step map (1 step = 1 code file)

| Step | Code file | Description |
|------|-----------|-------------|
| [Step 01](../steps/step_01_libcst_comments_behavior_check.md) | `tests/test_libcst_comment_behavior.py` | Blocking verification of LibCST comment/docstring preservation behavior |
| [Step 02](../steps/step_02_tree_snapshot_schema.md) | `code_analysis/core/database/base.py` | Add file-level snapshot schema for full tree/source storage |
| [Step 03](../steps/step_03_tree_nodes_schema_and_sibling_constraints.md) | `code_analysis/core/database/schema_sync.py` | Enforce node-table constraints and sibling order invariants |
| [Step 04](../steps/step_04_unified_file_sync_service.md) | `code_analysis/core/database/file_tree_sync.py` | Introduce unified file-level DB sync service used by all write flows |
| [Step 05](../steps/step_05_wire_cst_save_tree_flow.md) | `code_analysis/core/cst_tree/tree_saver.py` | Route tree-save flow through unified file-level sync service |
| [Step 06](../steps/step_06_wire_background_indexing_flow.md) | `code_analysis/commands/update_indexes_analyzer.py` | Route background indexing flow through same unified service |
| [Step 07](../steps/step_07_restore_policy_and_force_mode.md) | `code_analysis/commands/file_management.py` | Standardize DB->file restore safety/force behavior with backup |
| [Step 08](../steps/step_08_fidelity_and_roundtrip_tests.md) | `tests/test_file_tree_snapshot_fidelity.py` | End-to-end fidelity tests: full restore, comments/docstrings, sibling order, data types |

---

## Dependencies

- 01 is blocking and must be completed first.
- 02 -> 03 -> 04 is strict sequence.
- 05 and 06 depend on 04.
- 07 depends on 04.
- 08 depends on 01, 05, 06, 07.

Parallelizable chains are defined in [PARALLEL_CHAINS.md](PARALLEL_CHAINS.md).

---

## Global blackstops

- No separate write logic for tree-save and background indexing.
- No partial file success states.
- No DB overwrite of existing file in non-force mode.
- No node-order loss (sibling order must be stable and restorable).
- No content-loss for comments/docstrings/data types in accepted implementation.
- No partial implementation handoff.

---

## Final gate

- Execute full step checklist.
- Re-check all acceptance criteria from TZ.
- Confirm all touched files pass code_mapper, black, flake8, mypy.
- Confirm round-trip fidelity for comments, docstrings, sibling order, and data types.
