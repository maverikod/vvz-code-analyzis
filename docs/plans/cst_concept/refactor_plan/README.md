# Refactor plan steps (1 file = 1 step)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Plan index: [REFACTOR_PLAN.md](../REFACTOR_PLAN.md)

| File | Step |
|------|------|
| [step_01_get_file_lines.md](step_01_get_file_lines.md) | get_file_lines command |
| [step_02_cst_get_node_at_line.md](step_02_cst_get_node_at_line.md) | cst_get_node_at_line command |
| [step_03_skeleton_cst_load_file.md](step_03_skeleton_cst_load_file.md) | Skeleton (collapsed branches) in cst_load_file; multi-node request |
| [step_04_children_scope.md](step_04_children_scope.md) | children_depth: int or "direct" \| "recursive" in cst_get_node_info |
| [step_05_move_action.md](step_05_move_action.md) | move + precise positioning (__root__, first/last/after N) in cst_modify_tree |
| [step_06_apply_save_one_request.md](step_06_apply_save_one_request.md) | apply + save in one request; save failure = nothing changed, rollback |
