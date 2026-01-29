# Documentation Audit — Commands

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Summary

Re-audit of command documentation against code (schemas, return shapes, error codes). Each command is documented in a separate file under `docs/commands/<block>/<command_name>.md` with: purpose, arguments, returned data, examples (correct and incorrect), and error codes.

## Main deliverables

1. **[COMMANDS_GUIDE.md](COMMANDS_GUIDE.md)** — Main detailed guide:
   - Standard per-command doc structure (purpose, arguments, return, examples)
   - Links to all per-command files by block
   - Return format (success/error) and how to verify docs against code

2. **[COMMANDS_INDEX.md](COMMANDS_INDEX.md)** — Updated with a link to COMMANDS_GUIDE and clarification of “Related documentation”.

3. **Per-command docs** — All commands listed in COMMANDS_INDEX have a dedicated file in `docs/commands/<block>/<command_name>.md`. Structure is consistent: Purpose, Arguments (table), Returned data (Success/Error), Examples (correct/incorrect), Error codes summary, Best practices.

## Fixes applied

### create_project (`docs/commands/project_management/create_project.md`)

- **Arguments vs examples:** Examples used `watched_dir` and `project_dir`; the command schema uses `watch_dir_id` (UUID from `watch_dirs` table) and `project_name`. Examples were updated to use `watch_dir_id`, `project_name`, and `description`.
- **Returned data:** Doc claimed response included `already_existed`, `description`, `old_description`, `watch_dir_id`. The MCP command returns only `data.project_id` and `message`. Success section and “Return Values” were updated to match.
- **Error codes:** Doc listed codes that do not exist in `project_creation.py` (e.g. `WATCHED_DIR_NOT_FOUND`, `PROJECT_DIR_NOT_FOUND`). Replaced with actual codes: `WATCH_DIR_NOT_FOUND`, `INVALID_PROJECT_NAME`, `PROJECT_ALREADY_EXISTS`, `PROJECT_DIR_EXISTS`, `PROJECTID_WRITE_ERROR`, `DATABASE_REGISTRATION_ERROR`, `CREATE_PROJECT_ERROR`. Incorrect usage and error codes summary table were updated accordingly.

## Verification method

- **Arguments:** Compared with `get_schema()` in the command class (see COMMANDS_INDEX for file paths).
- **Return shape:** Inferred from `execute()` return (`SuccessResult`/`ErrorResult`) and constructor arguments.
- **Error codes:** Grep for `ErrorResult(..., code="...")` and `result.get("error", "...")` in the command and related modules.

## Optional commands (not documented here)

Commands registered in `hooks.py` with try/except (optional modules): `analyze_project`, `analyze_file`, `help`, `add_watch_dir`, `remove_watch_dir`. Their modules may be missing; only `check_vectors` is documented under misc. If those modules are added, create corresponding docs under `docs/commands/misc/` following the same structure.

## Next steps (recommendations)

- When adding or changing a command, update both the command’s `get_schema()`/`execute()` and the corresponding `docs/commands/<block>/<command_name>.md`.
- Run the same verification (schema, return shape, error codes) for new or modified commands.
- Keep COMMANDS_GUIDE and COMMANDS_INDEX in sync when adding new blocks or commands.
