# File split order (by difference from 400-line limit, descending)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Split files with >400 lines in this order (diff = lines - 400).

| Diff | Lines | File |
|------|-------|------|
| 770 | 1170 | code_analysis/commands/backup_mcp_commands.py |
| 756 | 1156 | code_analysis/core/svo_client_manager.py |
| 520 | 920 | code_analysis/main.py |
| 181 | 581 | code_analysis/core/database/base.py |
| 574 | 974 | code_analysis/core/database/schema_creation_create.py |
| 750 | 1150 | code_analysis/commands/cst_modify_tree_command.py |
| 731 | 1131 | code_analysis/core/cst_tree/tree_modifier_ops.py |
| 674 | 1074 | code_analysis/core/database/schema_sync.py |
| 668 | 1068 | code_analysis/commands/file_management.py |
| 655 | 1055 | code_analysis/core/file_watcher_pkg/multi_project_worker.py |
| 643 | 1043 | tests/test_config_driver.py |
| 547 | 947 | code_analysis/core/vectorization_worker_pkg/processing.py |
| 509 | 909 | code_analysis/commands/repair_worker_mcp_commands.py |
| 485 | 885 | code_analysis/commands/database_integrity_mcp_commands.py |
| ... | ... | (then all others >400) |

Target: no file >400 lines. After each split, re-run the list and continue.
