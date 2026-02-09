# list_project_files

**Command name:** `list_project_files`  
**Class:** `ListProjectFilesMCPCommand`  
**Source:** `code_analysis/commands/ast/list_files.py`  
**Category:** ast

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The list_project_files command lists all files in a project with metadata and statistics. It provides information about files including their paths, statistics (classes, functions, chunks, AST), and other metadata stored in the database.

Operation flow:
1. Validates root_dir exists and is a directory
2. Opens database connection
3. Resolves project_id (from parameter or inferred from root_dir)
4. Retrieves all project files from database (excluding deleted files)
5. If file_pattern provided, filters files using fnmatch pattern matching
6. Applies pagination: offset and limit
7. Returns list of files with metadata and statistics

File Metadata:
Each file entry includes:
- path: File path (relative to project root)
- id: Database file ID
- Statistics: classes count, functions count, chunks count, AST status
- Other metadata fields from database

Pattern Matching:
- Uses fnmatch pattern matching (shell-style wildcards)
- Examples: '*.py', 'src/*', 'tests/test_*.py'
- Case-sensitive matching

Use cases:
- Get catalog of all files in project
- Filter files by pattern (e.g., all Python files)
- Get file statistics and metadata
- Discover project structure
- Check which files have been analyzed

Important notes:
- Excludes deleted files from results
- Supports pagination with limit and offset
- Pattern matching uses fnmatch (shell wildcards)
- Returns total count before pagination

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | **Yes** | Project UUID (from create_project or list_projects). |
| `file_pattern` | string | No | Optional pattern to filter files (e.g., '*.py', 'core/*') |
| `limit` | integer | No | Optional limit on number of results |
| `offset` | integer | No | Offset for pagination Default: `0`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always true on success
- `files`: List of file dictionaries from database. Each contains:
- id: Database file ID
- path: File path (relative to project root)
- Statistics: classes count, functions count, chunks count, AST status
- Other metadata fields from database (created_at, updated_at, etc.)
- `count`: Number of files in current page (after pagination)
- `total`: Total number of files matching criteria (before pagination)
- `offset`: Offset used for pagination

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** PROJECT_NOT_FOUND, LIST_FILES_ERROR (and others).

---

## Examples

### Correct usage

**List all files in project**
```json
{
  "root_dir": "/home/user/projects/my_project"
}
```

Returns list of all files in the project with their metadata and statistics.

**List only Python files**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_pattern": "*.py"
}
```

Returns only files matching *.py pattern (all Python files).

**List files in specific directory**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_pattern": "src/*"
}
```

Returns only files in src/ directory.

**List files with pagination**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_pattern": "*.py",
  "limit": 100,
  "offset": 0
}
```

Returns first 100 Python files. Use offset for next page.

### Incorrect usage

- **PROJECT_NOT_FOUND**: root_dir='/path' but project not registered. Ensure project is registered. Run update_indexes first.

- **LIST_FILES_ERROR**: Database error, invalid parameters, or corrupted data. Check database integrity, verify parameters, ensure project has been analyzed.

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `PROJECT_NOT_FOUND` | Project not found in database | Ensure project is registered. Run update_indexes f |
| `LIST_FILES_ERROR` | General error during file listing | Check database integrity, verify parameters, ensur |

## Best practices

- Use file_pattern to filter files by type or location
- Use limit and offset for pagination with large projects
- Check total field to see total count before pagination
- Use this command to discover project structure
- Check file statistics to understand code distribution

---
