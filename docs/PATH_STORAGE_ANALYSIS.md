# Path Storage Analysis

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-11

## Database Schema

### Files Table

```sql
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    path TEXT NOT NULL,              -- Absolute path stored as TEXT
    lines INTEGER,
    last_modified REAL,
    has_docstring BOOLEAN,
    deleted BOOLEAN DEFAULT 0,
    original_path TEXT,              -- Original path before moving to version_dir
    version_dir TEXT,                -- Version directory path
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    UNIQUE(project_id, dataset_id, path)
)
```

**Key Points**:
- `path` column: `TEXT NOT NULL` - stores absolute file paths
- `original_path` column: `TEXT` - stores original path before file movement
- `version_dir` column: `TEXT` - stores version directory path for deleted files
- Unique constraint: `(project_id, dataset_id, path)` - ensures one file per project/dataset/path

## Path Storage Format

### 1. Storage Format: **Absolute Paths as Strings**

**Rule**: All file paths in database are stored as **absolute paths** (strings).

**Implementation**: 
- Paths are normalized to absolute before storing
- Stored as `TEXT` in SQLite (string)
- Example: `/home/vasilyvz/projects/tools/code_analysis/test_data/bhlff/main.py`

### 2. Path Normalization Functions

#### `normalize_path_simple(path: str | Path) -> str`

**Purpose**: Simple path normalization without project information.

**Algorithm**:
```python
def _normalize_path_simple_internal(path: str | Path) -> str:
    path_obj = Path(path)
    if not path_obj.is_absolute():
        path_obj = path_obj.expanduser().resolve()
    else:
        path_obj = path_obj.resolve()
    return str(path_obj)
```

**Steps**:
1. Convert to `Path` object
2. If relative path → expand `~` and resolve to absolute
3. If absolute path → resolve (follow symlinks, normalize)
4. Return as string

**Example**:
- Input: `./test_data/file.py` or `~/projects/file.py`
- Output: `/home/vasilyvz/projects/tools/code_analysis/test_data/file.py`

#### `normalize_file_path(file_path, watch_dirs=None, project_root=None) -> NormalizedPath`

**Purpose**: Full path normalization with project information.

**Algorithm**:
1. Normalize to absolute path using `_normalize_path_simple_internal()`
2. If `project_root` provided → use it directly
3. Otherwise, discover project from `watch_dirs`
4. Validate project_id from `projectid` file
5. Calculate relative path from project root
6. Return `NormalizedPath` with:
   - `absolute_path`: Absolute normalized path (string)
   - `project_root`: Project root directory (Path)
   - `project_id`: Project ID (UUID4 string)
   - `relative_path`: Relative path from project root (string)

## How Absolute Paths are Formed

### Process Flow

```
Input Path (any format)
    ↓
Path(path) - Convert to Path object
    ↓
Check if absolute?
    ├─ NO → expanduser().resolve()
    │        (expand ~, resolve symlinks, make absolute)
    │
    └─ YES → resolve()
              (resolve symlinks, normalize)
    ↓
str(path_obj) - Convert to string
    ↓
Store in database as TEXT
```

### Key Functions

1. **`Path.resolve()`**:
   - Resolves all symlinks in path
   - Normalizes path (removes `.`, `..`)
   - Makes path absolute
   - Example: `/home/user/../projects/./file.py` → `/home/projects/file.py`

2. **`Path.expanduser()`**:
   - Expands `~` to home directory
   - Example: `~/projects/file.py` → `/home/user/projects/file.py`

3. **`str(Path)`**:
   - Converts Path object to string
   - Uses platform-specific path separator (`/` on Unix, `\` on Windows)

### Examples

| Input | Normalization Process | Output (Absolute Path) |
|-------|----------------------|----------------------|
| `./file.py` | `Path('./file.py').resolve()` | `/home/vasilyvz/projects/tools/code_analysis/file.py` |
| `~/file.py` | `Path('~/file.py').expanduser().resolve()` | `/home/vasilyvz/file.py` |
| `/home/user/../projects/file.py` | `Path('/home/user/../projects/file.py').resolve()` | `/home/projects/file.py` |
| `/home/user/file.py` | `Path('/home/user/file.py').resolve()` | `/home/user/file.py` |

## Path Storage in Database Operations

### 1. Adding File (`add_file()`)

**Location**: `code_analysis/core/database/files.py`

**Process**:
```python
# Try to find project root
project_root = find_project_root_by_walking_up(path)

if project_root:
    # Use unified normalization with project validation
    normalized = normalize_file_path(path_obj, project_root=project_root)
    abs_path = normalized.absolute_path
    # Validate project_id matches
else:
    # Fallback to simple normalization
    abs_path = normalize_path_simple(path)

# Store in database
INSERT INTO files (project_id, dataset_id, path, ...) 
VALUES (?, ?, ?, ...)
```

**Result**: `path` column stores absolute path as string.

### 2. Getting File (`get_file_by_path()`)

**Location**: `code_analysis/core/database/files.py`

**Process**:
```python
# Normalize input path to absolute
abs_path = normalize_path_simple(path)

# Query database with normalized path
SELECT * FROM files WHERE path = ? AND project_id = ?
```

**Result**: Path is normalized before querying to ensure match.

### 3. Updating File (`update_file_data()`)

**Location**: `code_analysis/core/database/files.py`

**Process**:
```python
# Normalize path to absolute
abs_path = normalize_path_simple(file_path)

# Update or query with normalized path
UPDATE files SET ... WHERE path = ? AND project_id = ?
```

## Path Comparison

**Important**: Paths are compared as strings after normalization.

**Why this works**:
- All paths are normalized to absolute
- Symlinks are resolved
- Path separators are normalized
- Relative components (`.`, `..`) are resolved

**Example**:
- `/home/user/../projects/file.py` and `/home/projects/file.py` → both normalize to `/home/projects/file.py`
- Comparison: `normalize_path_simple(path1) == normalize_path_simple(path2)`

## Summary

1. **Storage Format**: Absolute paths stored as `TEXT` strings
2. **Normalization**: All paths normalized using `Path.resolve()` before storage
3. **Formation**: Absolute paths formed by:
   - Converting to `Path` object
   - Expanding `~` if relative
   - Resolving symlinks and normalizing
   - Converting back to string
4. **Comparison**: Paths compared as normalized strings
5. **Consistency**: All database operations normalize paths before storing/querying
