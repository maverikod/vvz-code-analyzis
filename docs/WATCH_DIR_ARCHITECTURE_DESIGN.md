# Watch Directory Architecture Design

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-11

## Key Design Decision

**File paths are stored as RELATIVE paths from project root, not absolute!**

**Absolute path calculation**:
```
absolute_path = watch_dir_paths.absolute_path + relative_path_from_project_root
```

## Database Schema

### 1. Table `watch_dirs`

Stores watch directory identifiers.

```sql
CREATE TABLE watch_dirs (
    id TEXT PRIMARY KEY,                    -- UUID4 identifier
    name TEXT,                              -- Human-readable name (optional)
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now'))
)
```

### 2. Table `watch_dir_paths`

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

**Note**: `absolute_path` can be NULL if:
- Watch dir exists in DB but not found in config
- Watch dir exists in config but path doesn't exist on disk

### 3. Table `projects` (Modified)

Add `watch_dir_id` to link project to watch directory.

```sql
ALTER TABLE projects ADD COLUMN watch_dir_id TEXT;
-- Add foreign key
-- Add index for performance
```

**Note**: `watch_dir_id` can be NULL for projects discovered before this change.

### 4. Table `files` (Modified)

**CRITICAL CHANGE**: Store RELATIVE path from project root, not absolute!

```sql
ALTER TABLE files ADD COLUMN watch_dir_id TEXT;
ALTER TABLE files ADD COLUMN relative_path TEXT;  -- NEW: relative from project root
-- Keep existing 'path' column for migration, but new code uses relative_path
```

**Migration strategy**:
- Keep `path` column (absolute) for backward compatibility
- Add `relative_path` column (relative from project root)
- Add `watch_dir_id` column
- Gradually migrate: new files use `relative_path`, old files keep `path`

**Future**: Eventually remove `path` column, use only `relative_path`.

### 5. Path Resolution

**Absolute path calculation**:
```python
def get_absolute_path(file_record: Dict, database: CodeDatabase) -> str:
    """
    Calculate absolute path from file record.
    
    Args:
        file_record: File record from database with relative_path and watch_dir_id
        database: Database instance
    
    Returns:
        Absolute path as string
    """
    if file_record.get('relative_path'):
        # New format: use relative_path + watch_dir_path
        watch_dir_id = file_record['watch_dir_id']
        watch_dir_path = database.get_watch_dir_path(watch_dir_id)
        if watch_dir_path:
            project_root = database.get_project_root(file_record['project_id'])
            # Calculate: watch_dir_path + (project_root relative to watch_dir) + relative_path
            # OR: project_root + relative_path (simpler)
            return str(Path(watch_dir_path) / project_root.relative_to(watch_dir_path) / file_record['relative_path'])
        else:
            raise ValueError(f"Watch dir {watch_dir_id} path not found")
    else:
        # Old format: use absolute path directly
        return file_record['path']
```

**Simpler approach**:
- Store `project_root` in `projects` table (already exists)
- Calculate: `project_root + relative_path = absolute_path`
- But we still need `watch_dir_id` for file linking

**Better approach**:
- Store `relative_path` from project root in `files` table
- Get `project_root` from `projects` table
- Calculate: `project_root + relative_path = absolute_path`
- `watch_dir_id` is for linking files to watch directories, not for path calculation

## File Path Storage

### Current (Absolute Paths)
```sql
files.path = '/home/user/projects/test_data/bhlff/main.py'  -- Absolute
```

### New (Relative Paths)
```sql
files.relative_path = 'main.py'  -- Relative from project root
projects.root_path = '/home/user/projects/test_data/bhlff'  -- Project root
-- Absolute = projects.root_path + files.relative_path
```

## Config Format

### Proposed Format

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

**Backward compatibility**: Support old format (string array), auto-generate UUID4.

## File Watcher Startup Logic

### Step 1: Load Config Watch Dirs

```python
for watch_dir_entry in config['code_analysis']['worker']['watch_dirs']:
    watch_dir_id = watch_dir_entry['id']  # or generate if old format
    watch_dir_path = Path(watch_dir_entry['path']).resolve()
    
    # Check if watch_dir exists in DB
    existing = database.get_watch_dir(watch_dir_id)
    if not existing:
        # Create new watch_dir entry
        database.create_watch_dir(watch_dir_id, name=watch_dir_path.name)
    
    # Update watch_dir_paths
    if watch_dir_path.exists():
        database.update_watch_dir_path(watch_dir_id, str(watch_dir_path))
    else:
        database.update_watch_dir_path(watch_dir_id, None)  # NULL if not found
```

### Step 2: Discover Projects

```python
for watch_dir_id in database.get_all_watch_dirs():
    watch_dir_path = database.get_watch_dir_path(watch_dir_id)
    if not watch_dir_path:
        continue  # Skip if path not found
    
    # Discover projects in watch_dir (max depth 1)
    projects = discover_projects_in_directory(Path(watch_dir_path))
    
    for project in projects:
        # Check if project exists in DB
        existing = database.get_project(project.project_id)
        if existing:
            # Update watch_dir_id if needed
            if existing['watch_dir_id'] != watch_dir_id:
                database.update_project_watch_dir(project.project_id, watch_dir_id)
        else:
            # Create new project
            database.create_project(
                project_id=project.project_id,
                root_path=str(project.root_path),
                watch_dir_id=watch_dir_id,
                ...
            )
```

### Step 3: Mark Missing Watch Dirs

```python
# For watch_dirs in DB but not in config
all_db_watch_dirs = database.get_all_watch_dirs()
config_watch_dir_ids = {wd['id'] for wd in config_watch_dirs}

for watch_dir_id in all_db_watch_dirs:
    if watch_dir_id not in config_watch_dir_ids:
        # Not in config - set path to NULL
        database.update_watch_dir_path(watch_dir_id, None)
```

## File Operations

### Adding File

```python
def add_file(path: str, project_id: str, ...):
    # Get project root
    project = database.get_project(project_id)
    project_root = Path(project['root_path'])
    
    # Normalize input path to absolute
    abs_path = normalize_path_simple(path)
    abs_path_obj = Path(abs_path)
    
    # Calculate relative path from project root
    try:
        relative_path = abs_path_obj.relative_to(project_root)
    except ValueError:
        raise ValueError(f"File {abs_path} is not within project root {project_root}")
    
    # Get watch_dir_id from project
    watch_dir_id = project['watch_dir_id']
    
    # Store relative path, not absolute
    database.insert_file(
        relative_path=str(relative_path),  # NEW: relative path
        watch_dir_id=watch_dir_id,         # NEW: watch_dir_id
        project_id=project_id,
        ...
    )
```

### Getting File

```python
def get_file_by_path(path: str, project_id: str):
    # Normalize input path
    abs_path = normalize_path_simple(path)
    abs_path_obj = Path(abs_path)
    
    # Get project
    project = database.get_project(project_id)
    project_root = Path(project['root_path'])
    
    # Calculate relative path
    relative_path = abs_path_obj.relative_to(project_root)
    
    # Query by relative_path
    return database.query_file(
        relative_path=str(relative_path),
        project_id=project_id
    )
```

### Getting Absolute Path

```python
def get_file_absolute_path(file_record: Dict):
    project = database.get_project(file_record['project_id'])
    project_root = Path(project['root_path'])
    
    if file_record.get('relative_path'):
        # New format
        return str(project_root / file_record['relative_path'])
    else:
        # Old format (backward compatibility)
        return file_record['path']
```

## Migration Plan

### Phase 1: Add New Columns
- Add `watch_dirs` table
- Add `watch_dir_paths` table
- Add `watch_dir_id` to `projects` table
- Add `watch_dir_id` and `relative_path` to `files` table

### Phase 2: Populate Watch Dirs
- Read config
- Create/update `watch_dirs` entries
- Create/update `watch_dir_paths` entries

### Phase 3: Migrate Projects
- Link existing projects to watch_dirs
- Update `projects.watch_dir_id`

### Phase 4: Migrate Files
- For each file:
  - Calculate `relative_path` from `path` and `project.root_path`
  - Set `watch_dir_id` from `project.watch_dir_id`
  - Update file record

### Phase 5: Switch to New Format
- New files use `relative_path`
- Old files gradually migrated
- Eventually remove `path` column

## Questions Remaining

1. **Path calculation**: Use `project_root + relative_path` or `watch_dir_path + project_relative + file_relative`?
   - **Answer**: Simpler is better - use `project_root + relative_path`

2. **Backward compatibility**: How long to keep `path` column?
   - **Answer**: Keep until all files migrated, then remove

3. **Performance**: Index on `relative_path`?
   - **Answer**: Yes, add index on `(project_id, relative_path)`
