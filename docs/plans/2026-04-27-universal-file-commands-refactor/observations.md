# Observations: universal file commands refactor

## 2026-04-28 plan audit against current code

### Current code reads

Verified through MCP commands against project `code_analysis` with project_id `8772a086-688d-4198-a0c4-f03817cc0e6c`.

Read files:

- `code_analysis/commands/project_text_file_guard.py`
- `code_analysis/commands/write_project_text_lines_command.py`
- `code_analysis/commands/read_project_text_file_command.py`
- `code_analysis/commands/file_management_mcp_commands/create_text_file.py`

List checks:

- `code_analysis/core/file_handlers/*` returned no files.
- `docs/plans/2026-04-27-universal-file-commands-refactor/steps/*.md` returned 23 step files.

### Findings

1. The plan previously implied that strict suffix checks still needed to be added to `write_project_text_lines`. Current code already has a strict allowlist for `.adoc`, `.md`, `.rst`, `.txt` and rejects Python / known source-code suffixes.
2. The remaining defect is not the absence of suffix checks. The remaining defect is that `write_project_text_lines` still calls `update_file_data_atomic_batch` after a text write.
3. `read_project_text_file` is not a simple plain-text reader for every suffix. It routes Python paths to `get_file_lines` and returns structured JSON for small `.json` files.
4. The earlier plan used ambiguous public command names `read/save/replace/delete`. The corrected plan requires explicit MCP command names: `universal_file_read`, `universal_file_save`, `universal_file_replace`, `universal_file_delete`.
5. The earlier plan suggested Python-like range strings for text edits. The corrected plan uses existing MCP convention: `start_line` and `end_line`, 1-based inclusive.
6. The earlier plan left `.toml` ambiguous. The corrected plan marks `.toml` unsupported until a TOML policy or handler is explicitly designed.
7. The existing step files are very short and are not yet sufficient for a `qwen 32B Q4_K_M` performer unless combined with the corrected README step contract.

## Reproduced bug

Command:
`write_project_text_lines` on `docs/plans/2026-04-27-universal-file-commands-refactor/README.md`

Expected:
Markdown/plain text write either succeeds safely or fails before side effects. Markdown must never be parsed as Python.

Actual:
The command returned success at proxy envelope level but command result success was false.

Error:
`UPDATE_FILE_DATA_ERROR`: `Failed to update file data: Syntax error: invalid decimal literal (README.md, line 7)`

Root cause:
`write_project_text_lines` writes allowed text suffixes, then calls `update_file_data_atomic_batch`, which is a code-oriented update path and can parse non-Python text as Python.

Fix:
Route text writes through a text-safe metadata update path, or make the file-data update layer handler-aware so non-Python text never enters Python AST/CST/entity parsing.

Post-fix verification:
Required after implementation:

1. run MCP write on a test `.md` file;
2. confirm `result.success=true` inside command result, not only queue/proxy status;
3. run a separate `read_project_text_file` command and confirm content changed;
4. confirm result/logs show no Python AST/CST/entity parsing path for Markdown;
5. record final behavior here.

Status:
Open.

## Plan-file update method

Because `write_project_text_lines` currently reproduces the Markdown update bug, plan markdown files were updated with `create_text_file` using `overwrite=true`. This command was verified in current code to write files on disk only and avoid DB/index sync.

Every changed plan file must still be verified with a separate `read_project_text_file` command.
