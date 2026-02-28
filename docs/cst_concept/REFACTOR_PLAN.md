# CST refactoring plan (step-by-step)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Scope and references

- **Concept and strategy:** [CST_CONCEPT_AND_PIPELINE.md](CST_CONCEPT_AND_PIPELINE.md) — skeleton load, node request modes, batch (node + action), write = nodes + file, syntax errors, comparison with direct editing.
- **Gap analysis:** [CST_COMMANDS_GAP_ANALYSIS.md](../analysis/CST_COMMANDS_GAP_ANALYSIS.md) — get_file_lines, cst_get_node_at_line, skeleton.

**Rule:** 1 code file = 1 step. Each step is in a separate file (see below). Each step is self-contained with references; each includes success metrics and mandatory post-code checks.

**Post-step checks (every step):**
- Search and fix: incomplete code, TODO, ellipsis/syntax violations, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations from project/plan rules.
- Run `code_mapper -r <project_code_dir>` and fix all reported errors.
- Run `mypy`, `flake8`, `black` and fix all reported issues.

---

## Step files (1 file = 1 step)

| Step | Description | File |
|------|-------------|------|
| 1 | `get_file_lines` command (raw lines without parsing) | [step_01_get_file_lines.md](refactor_plan/step_01_get_file_lines.md) |
| 2 | `cst_get_node_at_line` command (node + parent in one call) | [step_02_cst_get_node_at_line.md](refactor_plan/step_02_cst_get_node_at_line.md) |
| 3 | Skeleton in `cst_load_file` (collapsed branches: signatures, docstrings, pass+comment; multi-node request) | [step_03_skeleton_cst_load_file.md](refactor_plan/step_03_skeleton_cst_load_file.md) |
| 4 | Unify `children_depth` (int or "direct" \| "recursive") in `cst_get_node_info` | [step_04_children_scope.md](refactor_plan/step_04_children_scope.md) |
| 5 | `move` + precise positioning (parent/`__root__`, first/last/after N) in `cst_modify_tree` | [step_05_move_action.md](refactor_plan/step_05_move_action.md) |
| 6 | Apply + save in one request; on save failure nothing changed, clear error, rollback tree | [step_06_apply_save_one_request.md](refactor_plan/step_06_apply_save_one_request.md) |

---

## Step order and dependencies

| Step | Depends on | Main file(s) |
|------|------------|--------------|
| 1. get_file_lines | — | `get_file_lines_command.py` (new) |
| 2. cst_get_node_at_line | tree_builder, tree_metadata, tree_range_finder | `cst_get_node_at_line_command.py` (new) |
| 3. Skeleton in cst_load_file | — | `cst_load_file_command.py` |
| 4. children_scope in cst_get_node_info | — | `cst_get_node_info_command.py` |
| 5. move in cst_modify_tree | tree_modifier | `cst_modify_tree_command.py`, `tree_modifier.py` |
| 6. Apply + save in one request | cst_save_tree logic | `cst_modify_tree_command.py` |

Steps 1–4 can be done in parallel or any order. Step 5 before step 6 (step 6 builds on modify command).

---

## Document updates after implementation

- Update [docs/commands/cst/README.md](../commands/cst/README.md) and command index for new commands (get_file_lines, cst_get_node_at_line).
- Update [CST_CONCEPT_AND_PIPELINE.md](CST_CONCEPT_AND_PIPELINE.md) §6.7 “Possible extensions” to mark implemented items (get_file_lines, skeleton default, node+parent in one call).
- Add or update per-command docs under `docs/commands/` for new/updated parameters and behaviour.

### Status of document updates (all steps implemented)

- [x] [docs/commands/cst/README.md](../commands/cst/README.md) — command table includes get_file_lines, cst_get_node_at_line.
- [x] [docs/commands/cst/COMMANDS.md](../commands/cst/COMMANDS.md) — index includes get_file_lines, cst_get_node_at_line.
- [x] [CST_CONCEPT_AND_PIPELINE.md](CST_CONCEPT_AND_PIPELINE.md) §6.7 — get_file_lines, skeleton (return_format), node+parent (cst_get_node_at_line), selector in load request marked as **Implemented**.
- [x] Per-command docs: [cst_get_node_info.md](../commands/cst/cst_get_node_info.md) (children_depth int or "direct"|"recursive"), [cst_modify_tree.md](../commands/cst/cst_modify_tree.md) (move, position, __root__, project_id/file_path apply+save).
