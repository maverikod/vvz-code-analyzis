# Code Quality Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

All in `commands/code_quality_commands.py`. These commands inherit from `Command` (not BaseMCPCommand). Schema from `get_schema()`; metadata from `metadata()`.

---

## format_code — FormatCodeCommand

**Description:** Format Python code using Black.

**Behavior:** Accepts file_path (and optional root_dir/project_id); runs Black on the file and returns formatted content or writes to file.

---

## lint_code — LintCodeCommand

**Description:** Lint Python code using Flake8.

**Behavior:** Accepts file_path and optional config; runs Flake8 and returns list of lint issues (line, code, message).

---

## type_check_code — TypeCheckCodeCommand

**Description:** Type check Python code using mypy. If config_file not provided, auto-detects pyproject.toml in parent directories of file_path.

**Behavior:** Runs mypy on the given file/project and returns type errors and notes.
