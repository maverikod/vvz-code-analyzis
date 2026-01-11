# Watch Directory Architecture - Clarification Questions

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-11

## Proposed Architecture

1. **Table `watch_dirs`**: Stores watch directories with UUID4 as identifier
2. **All files**: Linked to `watch_dir_id` instead of (or in addition to?) `project_id`
3. **Config**: Each watch_dir entry contains UUID4
4. **Table `watch_dir_paths`**: Maps UUID4 to absolute normalized path
5. **File watcher on startup**:
   - Fills `watch_dir_paths` with absolute normalized paths for existing DB entries that exist on disk
   - Creates DB entries for new projects found on disk, adds to `watch_dir_paths`
   - Adds NULL paths for projects in DB but not found in config or on disk

## Questions for Clarification

### 1. Relationship between `watch_dir_id` and `project_id`

**Question**: How are `watch_dir_id` and `project_id` related?

**Options**:
- **A**: One `watch_dir` can contain multiple projects (one-to-many)
  - Example: `watch_dir=/test_data` contains projects `bhlff`, `vast_srv`
  - Files link to BOTH `watch_dir_id` AND `project_id`
  
- **B**: `watch_dir_id` replaces `project_id` for file linking
  - Files link only to `watch_dir_id`
  - Projects are still tracked separately but files don't reference them directly

**Current understanding**: One watch_dir can contain multiple projects (option A)

### 2. Files Table Schema

**Question**: Should `files` table have:
- **Option A**: `watch_dir_id` in addition to `project_id`
  ```sql
  CREATE TABLE files (
    ...
    project_id TEXT NOT NULL,
    watch_dir_id TEXT NOT NULL,  -- NEW
    ...
    FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id)
  )
  ```

- **Option B**: `watch_dir_id` replaces `project_id` for file linking
  ```sql
  CREATE TABLE files (
    ...
    watch_dir_id TEXT NOT NULL,  -- REPLACES project_id
    project_id TEXT,              -- Optional, for reference only
    ...
  )
  ```

**Current understanding**: Option A (both fields)

### 3. Watch Directory Table Schema

**Question**: What columns should `watch_dirs` table have?

**Proposed**:
```sql
CREATE TABLE watch_dirs (
    id TEXT PRIMARY KEY,           -- UUID4
    name TEXT,                     -- Human-readable name
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now'))
)
```

**Is this correct?**

### 4. Watch Directory Paths Table Schema

**Question**: What columns should `watch_dir_paths` table have?

**Proposed**:
```sql
CREATE TABLE watch_dir_paths (
    watch_dir_id TEXT PRIMARY KEY,  -- UUID4, FK to watch_dirs(id)
    absolute_path TEXT,              -- Absolute normalized path, NULL if not found
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id) ON DELETE CASCADE
)
```

**Is this correct?**
- Should `absolute_path` be `NOT NULL` or allow `NULL`?
- Should there be unique constraint on `absolute_path` (one path per watch_dir)?

### 5. Config Format

**Question**: How should watch_dirs be defined in `config.json`?

**Current format**:
```json
{
  "code_analysis": {
    "worker": {
      "watch_dirs": [
        "/home/vasilyvz/projects/tools/code_analysis/test_data"
      ]
    }
  }
}
```

**Proposed format**:
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

**Or**:
```json
{
  "code_analysis": {
    "worker": {
      "watch_dirs": {
        "550e8400-e29b-41d4-a716-446655440000": "/home/vasilyvz/projects/tools/code_analysis/test_data"
      }
    }
  }
}
```

**Which format is preferred?**

### 6. File Watcher Startup Logic

**Question**: Clarify the startup sequence:

**Step 1**: "Fill `watch_dir_paths` with absolute normalized paths for existing DB entries that exist on disk"
- Does this mean: For each `watch_dir_id` in DB, if path exists on disk → update `watch_dir_paths.absolute_path`?

**Step 2**: "Create DB entries for new projects found on disk, add to `watch_dir_paths`"
- Does this mean: 
  - Scan config watch_dirs
  - For each watch_dir in config:
    - If `watch_dir_id` not in DB → create `watch_dirs` entry
    - If path exists on disk → create/update `watch_dir_paths` entry
  - Discover projects in watch_dir (via `projectid` files)
  - Create `projects` entries for new projects?

**Step 3**: "Add NULL paths for projects in DB but not found in config or on disk"
- Does this mean:
  - For each `watch_dir_id` in DB:
    - If not in config → set `watch_dir_paths.absolute_path = NULL`
    - If in config but path doesn't exist on disk → set `watch_dir_paths.absolute_path = NULL`?

**Is this correct?**

### 7. Migration of Existing Data

**Question**: How to handle existing data?

**Current state**:
- `files` table has `project_id` but no `watch_dir_id`
- No `watch_dirs` table
- No `watch_dir_paths` table

**Migration strategy**:
- Create `watch_dirs` table
- Create `watch_dir_paths` table
- For each existing project:
  - Find watch_dir that contains project's `root_path`
  - Create `watch_dir` entry (generate UUID4)
  - Create `watch_dir_paths` entry
  - Update `files` table: add `watch_dir_id` column, populate from project's watch_dir

**Is this correct?**
- What if project's `root_path` is not in any current watch_dir?
- Should we create a "default" watch_dir for orphaned projects?

### 8. Project Discovery

**Question**: How are projects discovered?

**Current logic**: 
- Scan watch_dir for `projectid` files (max depth 1)
- Create `projects` entry for each found project

**New logic**:
- Same discovery process
- But projects should also be linked to `watch_dir_id`?

**Should `projects` table have `watch_dir_id` column?**
```sql
CREATE TABLE projects (
    ...
    watch_dir_id TEXT,  -- NEW, FK to watch_dirs(id)
    FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id)
)
```

### 9. File Path Resolution

**Question**: How to determine `watch_dir_id` for a file?

**Current logic**:
- Find project root by walking up from file path
- Use project's `project_id`

**New logic**:
- Find project root (same as before)
- Find which `watch_dir` contains this project
- Use that `watch_dir_id`

**Is this correct?**

### 10. Backward Compatibility

**Question**: Should old config format (simple string array) still work?

**Current**:
```json
"watch_dirs": ["/path1", "/path2"]
```

**New**:
```json
"watch_dirs": [
  {"id": "uuid1", "path": "/path1"},
  {"id": "uuid2", "path": "/path2"}
]
```

**Should we support both formats?**
- If old format: auto-generate UUID4 for each path?
