# type_check_code

**Command name:** `type_check_code`  
**Class:** `TypeCheckCodeCommand`  
**Source:** `code_analysis/commands/code_quality_commands.py`  
**Category:** code_quality

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The type_check_code command performs static type checking on Python code using mypy. It analyzes type annotations and detects type errors, missing type hints, and type inconsistencies without running the code.

Operation flow:
1. Validates file_path exists and is a file
2. If config_file provided, validates it exists
3. If config_file not provided, auto-detects pyproject.toml in parent directories
4. If config points to this repository, runs mypy on entire package
5. Otherwise, runs mypy on single file
6. Executes mypy via subprocess with sanitized PYTHONPATH
7. Collects type errors from stdout and stderr
8. Returns success status and list of errors

Type Checking Behavior:
- Analyzes type annotations (function parameters, return types, variables)
- Detects type mismatches and inconsistencies
- Checks for missing type hints
- Validates generic types and type aliases
- Respects mypy configuration from config_file
- File is not modified (read-only analysis)

Config File Detection:
- If config_file not provided, searches for pyproject.toml in:
  1. File's parent directory
  2. Parent's parent directory (and up)
- Stops at first found pyproject.toml
- If config points to this repository, runs package-level check
- Otherwise, runs file-level check

Package vs File Mode:
- Package mode: Runs 'mypy -p code_analysis' (checks entire package)
  - Avoids duplicate module discovery issues
  - Better relative import resolution
  - More comprehensive type checking
- File mode: Runs 'mypy file.py' (checks single file)
  - Faster for single file checks
  - May have issues with relative imports

Use cases:
- Validate type annotations before committing
- Find type errors without running code
- Ensure type safety across codebase
- Check type hints completeness
- Validate generic types and type aliases
- Enforce type checking in CI/CD pipelines

Important notes:
- File is not modified (type checking is read-only)
- Requires mypy to be installed
- PYTHONPATH is sanitized to avoid import conflicts
- Package mode is used when config points to this repository
- ignore_errors=True treats errors as warnings (still returns errors list)
- success=True means no type errors found
- success=False means type errors were found (check errors list)

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_path` | string | **Yes** | Path to Python file to type check. |
| `config_file` | string | No | Optional path to mypy config file (e.g. pyproject.toml). |
| `ignore_errors` | boolean | No | If True, treat errors as warnings. Default: `false`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `file_path`: Path to type-checked file
- `config_file`: Path to mypy config file used (None if auto-detected or not found)
- `success`: True if no type errors found (or ignore_errors=True), False if type errors found and ignore_errors=False
- `error`: Error message if type checking failed (None if successful)
- `errors`: List of type error strings. Each error follows format: file_path:line:column: error_type: error_message
- `error_count`: Number of type errors found

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** FILE_NOT_FOUND, NOT_A_FILE, CONFIG_NOT_FOUND, INTERNAL_ERROR (and others).

---

## Examples

### Correct usage

**Type check a Python file**
```json
{
  "file_path": "/home/user/projects/my_project/src/main.py"
}
```

Type checks main.py using auto-detected mypy config. Returns all type errors found.

**Type check with explicit config**
```json
{
  "file_path": "/home/user/projects/my_project/src/main.py",
  "config_file": "/home/user/projects/my_project/pyproject.toml"
}
```

Type checks main.py using specified mypy config file. If config points to this repo, runs package-level check.

**Type check with errors as warnings**
```json
{
  "file_path": "./code_analysis/commands/backup_mcp_commands.py",
  "ignore_errors": true
}
```

Type checks file but treats errors as warnings. Returns success=True even if errors found (errors still in list).

### Incorrect usage

- **FILE_NOT_FOUND**: file_path='/path/to/nonexistent.py'. Verify file path is correct and file exists

- **NOT_A_FILE**: file_path='/path/to/directory'. Ensure path points to a file, not a directory

- **CONFIG_NOT_FOUND**: config_file='/path/to/missing/pyproject.toml'. Verify config file path is correct and file exists

- **INTERNAL_ERROR**: Unexpected exception in type checking logic. Check logs for details, verify file permissions and mypy installation

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `FILE_NOT_FOUND` | File does not exist | Verify file path is correct and file exists |
| `NOT_A_FILE` | Path is not a file (e.g., directory) | Ensure path points to a file, not a directory |
| `CONFIG_NOT_FOUND` | Config file specified but not found | Verify config file path is correct and file exists |
| `INTERNAL_ERROR` | Internal error during type checking | Check logs for details, verify file permissions an |

## Best practices

- Run type_check_code after adding type hints to validate them
- Fix all type errors before committing code
- Use ignore_errors=True for gradual type checking adoption
- Check error_count field to quickly see if issues exist
- Review errors list to understand type issues
- Run type_check_code in CI/CD pipelines to enforce type safety
- Use config_file for project-specific mypy settings
- Package mode (when config points to repo) provides better type checking

---
