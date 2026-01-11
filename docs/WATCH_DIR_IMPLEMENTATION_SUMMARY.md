# Watch Directory Implementation Summary

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-11

## Implementation Status

✅ **COMPLETED**: All required changes have been implemented.

## Architecture

**Database Access Chain**: `UserProcess -> CodeDatabase -> SpecificDriver (SQLiteDriverProxy)`

All database operations go through `CodeDatabase` which uses `SQLiteDriverProxy` for SQLite.

## Database Schema Changes

### 1. New Table: `watch_dirs`

Stores watch directory identifiers.

```sql
CREATE TABLE watch_dirs (
    id TEXT PRIMARY KEY,                    -- UUID4 identifier
    name TEXT,                              -- Human-readable name (optional)
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now'))
)
```

### 2. New Table: `watch_dir_paths`

Maps watch_dir_id to absolute normalized path.

```sql
CREATE TABLE watch_dir_paths (
    watch_dir_id TEXT PRIMARY KEY,          -- UUID4, FK to watch_dirs(id)
    absolute_path TEXT,                     -- Absolute normalized path, NULL if not found
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id) ON DELETE CASCADE
)
```

### 3. Modified Table: `projects`

Added `watch_dir_id` column.

```sql
ALTER TABLE projects ADD COLUMN watch_dir_id TEXT;
-- Foreign key to watch_dirs(id) ON DELETE SET NULL
-- Index on watch_dir_id for performance
```

**Columns**:
- `id` - Project identifier (UUID4 from projectid file)
- `name` - Project directory name
- `watch_dir_id` - Watch directory identifier (UUID4)

### 4. Modified Table: `files`

Added `watch_dir_id` and `relative_path` columns.

```sql
ALTER TABLE files ADD COLUMN watch_dir_id TEXT;
ALTER TABLE files ADD COLUMN relative_path TEXT;
-- Foreign key to watch_dirs(id) ON DELETE SET NULL
```

**Path Storage**:
- `path` - Absolute path (kept for compatibility, but new code uses relative_path)
- `relative_path` - Relative path from project root (NEW, preferred)
- `watch_dir_id` - Watch directory identifier (NEW)

**Absolute path calculation**:
```
absolute_path = project_root + relative_path
```

## Config Format

### New Format (Required)

```json
{
  "code_analysis": {
    "worker": {
      "watch_dirs": [
        {
          "id": "550e8400-e29b-41d4-a716-446655440000",
          "path": "/home/vasilyvz/projects/tools/code_analysis/test_data"
        }
      ]
    }
  }
}
```

**Old format (string array) is NOT supported**.

## File Watcher Startup Logic

### Initialization Sequence

1. **Read Config**: Load watch_dirs from config.json
2. **Create Watch Dir Entries**: For each watch_dir in config:
   - Create/update `watch_dirs` entry
   - Update `watch_dir_paths` with absolute normalized path (if exists on disk)
   - Set NULL if path doesn't exist on disk
3. **Discover Projects**: For each watch_dir:
   - Scan for `projectid` files (max depth 1)
   - Create/update `projects` entries with `watch_dir_id`
   - Only directories with `projectid` are processed
4. **Mark Missing**: For watch_dirs in DB but not in config:
   - Set `watch_dir_paths.absolute_path = NULL`

### Implementation

**Location**: `code_analysis/core/file_watcher_pkg/multi_project_worker.py`

**Method**: `_initialize_watch_dirs(database)`

Called on first successful database connection in `run()` method.

## Database Methods

### Watch Dirs Module

**Location**: `code_analysis/core/database/watch_dirs.py`

**Methods**:
- `create_watch_dir(watch_dir_id, name)` - Create watch directory entry
- `get_watch_dir(watch_dir_id)` - Get watch directory by ID
- `get_all_watch_dirs()` - Get all watch directories
- `update_watch_dir_path(watch_dir_id, absolute_path)` - Update path mapping
- `get_watch_dir_path(watch_dir_id)` - Get absolute path for watch directory
- `get_watch_dir_by_path(absolute_path)` - Get watch directory by path
- `get_all_watch_dir_paths()` - Get all path mappings
- `delete_watch_dir(watch_dir_id)` - Delete watch directory

### Files Module Updates

**Location**: `code_analysis/core/database/files.py`

**Updated Methods**:
- `get_file_by_path()` - Now uses `relative_path` for searching
- `add_file()` - Stores `relative_path` and `watch_dir_id`
- `get_file_id()` - Uses `relative_path` for searching
- `get_file_absolute_path()` - Calculates absolute path from `relative_path + project_root`

## Path Formation

### Storage

- **Relative path**: Stored in `files.relative_path` (relative from project root)
- **Absolute path**: Calculated as `project_root + relative_path`

### Example

```
Project root: /home/user/projects/test_data/bhlff
File: /home/user/projects/test_data/bhlff/main.py

Stored:
- relative_path: "main.py"
- path: "/home/user/projects/test_data/bhlff/main.py" (for compatibility)

Calculated:
- absolute_path = project_root + relative_path
- absolute_path = "/home/user/projects/test_data/bhlff" + "main.py"
- absolute_path = "/home/user/projects/test_data/bhlff/main.py"
```

## Project Discovery Rules

1. **CRITICAL**: Directory without `projectid` is NOT a project
2. **Strict Rule**: `projectid` can be ONLY at depth 0 or 1 from `watch_dir`:
   - `watch_dir/projectid` - ✅ allowed (level 0)
   - `watch_dir/dirA/projectid` - ✅ allowed (level 1)
   - `watch_dir/dirA/dirB/projectid` - ❌ NOT allowed (level 2 - ignored)
3. Only directories identified as projects are processed
4. Other directories are simply ignored

## Files Modified

1. ✅ `code_analysis/core/database/base.py` - Schema definitions
2. ✅ `code_analysis/core/database/watch_dirs.py` - NEW module
3. ✅ `code_analysis/core/database/__init__.py` - Added watch_dirs module
4. ✅ `code_analysis/core/database/files.py` - Updated for relative_path
5. ✅ `code_analysis/core/file_watcher_pkg/multi_project_worker.py` - Startup logic
6. ✅ `code_analysis/core/file_watcher_pkg/runner.py` - Updated signature
7. ✅ `code_analysis/core/worker_manager.py` - Updated signature
8. ✅ `code_analysis/main.py` - Config parsing

## Migration

**No migration needed** - database will be deleted and recreated.

## Testing Checklist

- [ ] Database schema creates correctly
- [ ] Watch dirs initialized on startup
- [ ] Projects discovered and linked to watch_dir_id
- [ ] Files stored with relative_path
- [ ] File search works with relative_path
- [ ] Absolute path calculation works correctly
- [ ] Config format validation works
- [ ] Missing watch_dirs get NULL paths
