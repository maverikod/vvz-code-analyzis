# Step 1: `get_file_lines` command (raw lines without parsing)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**Plan index:** [REFACTOR_PLAN.md](../REFACTOR_PLAN.md)

---

## Goal

Replace direct file read when the file has syntax errors or when only a line range is needed. No parsing.

## File to add

`code_analysis/commands/get_file_lines_command.py`

## Behaviour

- Input: `project_id`, `file_path`, `start_line`, `end_line` (1-based, inclusive).
- Resolve path via project (same as other CST commands).
- Read file as text; return lines in range (no LibCST). Response: `lines` (list of strings), `start_line`, `end_line`, `file_path`.
- Handle missing file / invalid range (e.g. start_line > end_line) with clear error codes.

## References

- Gap analysis “Option A — Raw lines (non-CST)”: [CST_COMMANDS_GAP_ANALYSIS.md](../../analysis/CST_COMMANDS_GAP_ANALYSIS.md)

## Registration

Register in `code_analysis/hooks.py` (try/except ImportError pattern).

## Success metrics

- Command appears in `list_servers` / schema for code-analysis-server.
- For a valid .py file and range, response contains exact `lines` for that range.
- For a file with syntax errors, response still returns raw lines (no parse).
- `start_line`/`end_line` out of range or empty file: defined error response, no crash.

## Post-step checks

- Search and fix: incomplete code, TODO, ellipsis/syntax violations, `pass` outside exceptions, `NotImplemented` outside abstract methods, deviations from project/plan rules.
- Run `code_mapper -r <project_code_dir>` and fix all reported errors.
- Run `mypy`, `flake8`, `black` and fix all reported issues.
