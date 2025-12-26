# File Watcher Architecture and Implementation Plan

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Overview

This document describes the architecture and implementation plan for file watching, cleanup, and version management in the code analysis system.

## Requirements

1. Add `deleted` flag to files table in database
2. Add command to clean up deleted files (hard delete)
3. Add command to collapse file versions (keep only latest by `last_modified`)
4. Add parallel process to track changed files in configured directories
5. Database `last_modified` comparison with file `mtime` - changed files should be queued
6. Worker with `.lock` file for process locking, running in separate process
7. **CRITICAL**: Files marked as `deleted` should NOT be chunked/processed
8. **CRITICAL**: All search/list operations should exclude `deleted=1` files by default, unless `include_deleted=True` parameter is provided
9. Only process code files and config files (ignore .pyc, __pycache__, etc.)
10. Get `watch_dirs` from same place as vectorization worker (`code_analysis.worker.watch_dirs`)

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Main Server Process                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Vectorization Worker (existing)                     │  │
│  │  - Processes chunks                                  │  │
│  │  - Adds to FAISS                                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  File Watcher Worker (new)                          │  │
│  │  - Scans watch_dirs from config                     │  │
│  │  - Compares mtime with DB last_modified            │  │
│  │  - Marks changed files for processing              │  │
│  │  - Uses .lock file per directory                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Database Schema Changes

### 1. Add `deleted` flag and path tracking to `files` table

```sql
ALTER TABLE files ADD COLUMN deleted BOOLEAN DEFAULT 0;
ALTER TABLE files ADD COLUMN original_path TEXT;
ALTER TABLE files ADD COLUMN version_dir TEXT;
CREATE INDEX idx_files_deleted ON files(deleted) WHERE deleted = 1;
```

**Rationale**: 
- `deleted`: Soft delete allows recovery
- `original_path`: Stores original file path before moving to version directory
- `version_dir`: Stores path to version directory where deleted file is stored
- Index for efficient queries
- Partial index (WHERE deleted = 1) for better performance

**File Movement Logic**:
- When marking as deleted: Move file from `path` to `version_dir`, store original `path` in `original_path`
- When unmarking: Move file from `version_dir` back to `original_path`, clear `original_path` and `version_dir`

### 2. Version tracking (via `last_modified`)

**Note**: Versions are tracked via `last_modified` timestamp. Multiple records with same `path` but different `last_modified` are considered different versions.

**No additional column needed** - version = `last_modified` timestamp.

**For version collapse**:
- Find all records with same `path` and `project_id`
- Keep only the one with latest `last_modified`
- Delete others (hard delete)

## Component Architecture

### 1. File Watcher Worker

**Location**: `code_analysis/core/file_watcher_pkg/`

**Structure**:
```
file_watcher_pkg/
├── __init__.py
├── base.py              # FileWatcherWorker class
├── scanner.py           # Directory scanning logic
├── processor.py          # File change detection and queuing
├── lock_manager.py       # .lock file management
└── runner.py            # Process entry point
```

**Key Components**:

#### `FileWatcherWorker` (base.py)
```python
class FileWatcherWorker:
    """
    Worker for tracking file changes in configured directories.
    
    Responsibilities:
    - Scan root watch_dirs from config (recursively)
    - Compare file mtime with DB last_modified
    - Mark changed files for processing
    - Handle .lock files for process locking (only at root level)
    
    Note: Lock files are created only in root watched directories
    from config, not in subdirectories.
    """
    
    def __init__(
        self,
        db_path: Path,
        project_id: str,
        watch_dirs: List[Path],  # Root directories from config
        scan_interval: int = 60,  # seconds
        lock_file_name: str = ".file_watcher.lock",
    ):
        """
        Initialize file watcher worker.
        
        Args:
            watch_dirs: List of root directories to watch (from config).
                       Lock files will be created only in these root directories.
        """
        ...
    
    async def scan_and_process(self) -> Dict[str, Any]:
        """
        Main scanning loop.
        
        For each root watched directory:
        1. Acquire lock (in root directory)
        2. Scan recursively for changes
        3. Process changes
        4. Release lock
        """
        ...
```

#### `LockManager` (lock_manager.py)
```python
class LockManager:
    """
    Manages .lock files for process locking.
    
    Each root watched directory from config gets its own .lock file containing:
    - Process ID
    - Timestamp
    - Worker name
    
    Lock files are created only in root watched directories, not in subdirectories.
    """
    
    def acquire_lock(self, root_directory: Path) -> bool:
        """
        Try to acquire lock for root watched directory.
        
        Args:
            root_directory: Root watched directory from config (not subdirectory)
        
        Returns:
            True if successful, False if already locked
        """
        ...
    
    def release_lock(self, root_directory: Path) -> None:
        """Release lock for root watched directory."""
        ...
    
    def is_locked(self, root_directory: Path) -> bool:
        """Check if root directory is locked by another process."""
        ...
    
    def get_lock_info(self, root_directory: Path) -> Optional[Dict[str, Any]]:
        """Get lock information (PID, timestamp, etc.) for root directory."""
        ...
```

#### `FileScanner` (scanner.py)
```python
class FileScanner:
    """
    Scans root watched directories for Python files and detects changes.
    
    Scans recursively from root watched directories, but lock files
    are only checked/created at root level.
    """
    
    async def scan_directory(
        self,
        root_directory: Path,  # Root watched directory from config
        database: CodeDatabase,
        project_id: str,
    ) -> Dict[str, Any]:
        """
        Scan root directory recursively and return statistics.
        
        Only processes:
        - Python files: `*.py`
        - Config files: `*.json`, `*.yaml`, `*.yml`, `*.toml`, `*.ini`, `*.cfg`
        
        Ignores:
        - `__pycache__/` directories
        - `.pyc` files
        - `.git/` directories
        - Other non-code files
        
        Returns:
        - new_files: List of new files found (not in DB)
        - changed_files: List of changed files (mtime != last_modified in DB)
        - deleted_files: List of files in DB but not on disk
        
        Scans all subdirectories but lock is only at root level.
        """
        ...
```

#### `FileProcessor` (processor.py)
```python
class FileProcessor:
    """
    Processes file changes and queues them for analysis.
    """
    
    async def process_changed_files(
        self,
        changed_files: List[Path],
        database: CodeDatabase,
        project_id: str,
    ) -> int:
        """
        Process changed files:
        1. Check if file is marked as deleted - if yes, skip
        2. Update last_modified in DB
        3. Mark file as needing chunking (delete existing chunks)
        4. Return count of processed files
        
        Files with deleted=1 are never processed.
        """
        ...
    
    async def mark_deleted_files(
        self,
        deleted_files: List[str],
        database: CodeDatabase,
        project_id: str,
        reason: Optional[str] = None,
    ) -> int:
        """
        Mark files as deleted (soft delete):
        1. Set deleted = 1
        2. Update updated_at
        3. Return count of marked files
        
        Files marked as deleted:
        - Will NOT be chunked
        - Will NOT be processed
        - Will be excluded from searches by default
        - Can be recovered with unmark_file_deleted()
        - Chunks are kept until hard delete
        """
        ...
```

### 2. Database Methods

**Location**: `code_analysis/core/database/files.py`

**New Methods**:

```python
def mark_file_deleted(self, file_path: str, project_id: str) -> bool:
    """Mark file as deleted (soft delete)."""
    ...

def get_deleted_files(self, project_id: str) -> List[Dict[str, Any]]:
    """Get all deleted files for a project."""
    ...

def hard_delete_file(self, file_id: int) -> None:
    """Permanently delete file and all related data."""
    ...

def collapse_file_versions(
    self, 
    project_id: str, 
    keep_latest: bool = True
) -> Dict[str, Any]:
    """
    Collapse file versions, keeping only latest by last_modified.
    
    Finds all records with same path but different last_modified.
    Keeps the one with latest last_modified, deletes others (hard delete).
    
    Returns:
        - kept_count: Number of versions kept
        - deleted_count: Number of versions deleted
    """
    ...

def get_file_versions(
    self, 
    file_path: str, 
    project_id: str
) -> List[Dict[str, Any]]:
    """
    Get all versions of a file (same path, different last_modified).
    
    Returns list sorted by last_modified (newest first).
    """
    ...

def mark_file_deleted(
    self,
    file_path: str,
    project_id: str,
    version_dir: str,
    reason: Optional[str] = None,
) -> bool:
    """
    Mark file as deleted (soft delete) and move to version directory.
    
    Process:
    1. Move file from original path to version directory
    2. Store original path in original_path column
    3. Store version directory in version_dir column
    4. Set deleted=1, update updated_at
    5. File will NOT be chunked or processed
    
    Args:
        file_path: Original file path (will be moved)
        project_id: Project ID
        version_dir: Directory where deleted files are stored
        reason: Optional reason for deletion
    
    Returns:
        True if file was found and marked, False otherwise
    """
    ...

def unmark_file_deleted(
    self,
    file_path: str,
    project_id: str,
) -> bool:
    """
    Unmark file as deleted (recovery) and move back to original location.
    
    Process:
    1. Get original_path and version_dir from database
    2. Move file from version_dir back to original_path
    3. Clear original_path and version_dir columns
    4. Set deleted=0, update updated_at
    5. File will be processed again
    
    Args:
        file_path: Current file path (in version directory) or original_path
        project_id: Project ID
    
    Returns:
        True if file was found and unmarked, False otherwise
    """
    ...

def get_deleted_files(
    self,
    project_id: str,
) -> List[Dict[str, Any]]:
    """
    Get all deleted files for a project.
    
    Returns files where deleted=1.
    """
    ...

def hard_delete_file(
    self,
    file_id: int,
) -> None:
    """
    Permanently delete file and all related data (hard delete).
    
    This is final deletion - removes:
    - File record
    - All chunks (and removes from FAISS)
    - All classes, functions, methods
    - All AST trees
    - All vector indexes
    
    Use with caution - cannot be recovered.
    """
    ...
```

### 3. CLI Commands

**Location**: `code_analysis/commands/`

#### `cleanup_deleted_files_command.py`
```python
class CleanupDeletedFilesCommand(BaseMCPCommand):
    """
    Command to clean up deleted files from database.
    
    Options:
    - dry_run: Show what would be deleted without actually deleting
    - older_than_days: Only delete files deleted more than N days ago
    - hard_delete: Permanently delete (default: soft delete)
    """
    ...
```

#### `collapse_versions_command.py`
```python
class CollapseVersionsCommand(BaseMCPCommand):
    """
    Command to collapse file versions, keeping only latest by last_modified.
    
    Finds all records with same path but different last_modified.
    Keeps the one with latest last_modified, deletes others (hard delete).
    
    Options:
    - project_id: Specific project (optional, all projects if not specified)
    - dry_run: Show what would be collapsed without actually deleting
    - keep_latest: Keep latest version (default: True)
    
    Hard delete removes all data for old versions.
    """
    ...
```

## Implementation Plan

### Phase 1: Database Schema Updates

1. **Add `deleted`, `original_path`, `version_dir` columns to `files` table**
   - Migration script
   - Update `_create_schema()` in `database/base.py`
   - Add index for performance
   - `original_path`: Stores original file path before moving to version directory
   - `version_dir`: Stores path to version directory where deleted file is stored

2. **Add database methods with file movement**
   - `mark_file_deleted(file_path, project_id, version_dir, reason)` - Move file to version dir, set deleted=1
   - `unmark_file_deleted(file_path, project_id)` - Move file back to original_path, set deleted=0
   - `get_deleted_files(project_id)` - Get all deleted files
   - `hard_delete_file(file_id)` - Permanently delete (remove physical file from version_dir, cascade DB)
   - `collapse_file_versions(project_id, keep_latest)` - Collapse versions, keep latest

### Phase 2: File Watcher Worker

1. **Create `file_watcher_pkg` package**
   - Base worker class
   - Lock manager
   - Scanner
   - Processor

2. **Integrate with main server**
   - Add to `main.py` startup
   - Configure from `config.json`
   - Separate process (like vectorization worker)

3. **Configuration**
   
   **Important**: `watch_dirs` are taken from `code_analysis.worker.watch_dirs` (same as vectorization worker).
   
   Additional file watcher config:
   ```json
   {
     "code_analysis": {
       "worker": {
         "watch_dirs": ["/path/to/dir1", "/path/to/dir2"]
       },
       "file_watcher": {
         "enabled": true,
         "scan_interval": 60,
         "lock_file_name": ".file_watcher.lock",
         "log_path": "logs/file_watcher.log"
       }
     }
   }
   ```

### Phase 3: CLI Commands

1. **Cleanup command**
   - Implement `CleanupDeletedFilesCommand`
   - Parameters: `dry_run`, `older_than_days`, `hard_delete`
   - Hard delete removes physical file from version_dir and all DB data
   - Register in command registry
   - Add MCP command

2. **Unmark deleted file command**
   - Implement `UnmarkDeletedFileCommand`
   - Parameters: `file_path`, `project_id`, `dry_run`
   - Moves file from version_dir back to original_path
   - Clears deleted flag, original_path, version_dir
   - Register in command registry
   - Add MCP command

3. **Collapse versions command**
   - Implement `CollapseVersionsCommand`
   - Register in command registry
   - Add MCP command

### Phase 4: Integration and Testing

1. **Test file watcher**
   - Test lock file mechanism
   - Test change detection
   - Test queuing

2. **Test cleanup commands**
   - Test soft delete
   - Test hard delete
   - Test version collapse

## File Change Detection Strategy

### Option 1: Polling (Recommended)

**Pros**:
- Simple implementation
- Works on all filesystems
- No external dependencies
- Reliable

**Cons**:
- CPU usage (mitigated by scan_interval)
- Slight delay in detection

**Implementation**:
```python
async def detect_changes(
    file_path: Path,
    db_record: Dict[str, Any],
) -> bool:
    """Check if file has changed."""
    file_mtime = file_path.stat().st_mtime
    db_mtime = db_record.get("last_modified")
    
    if db_mtime is None:
        return True  # New file
    
    # Compare with small tolerance for filesystem precision
    return abs(file_mtime - db_mtime) > 0.1
```

### Option 2: Filesystem Events (Alternative)

**Pros**:
- Real-time detection
- Lower CPU usage

**Cons**:
- Platform-specific (watchdog library)
- May miss events on some filesystems
- More complex

**Recommendation**: Start with polling, can add event-based later if needed.

## Lock File Format

**Location**: `{watch_dir}/.file_watcher.lock`

**Important**: Lock file is created **only in root watched directories** from config, not in subdirectories.

**Example**:
- Config: `watch_dirs: ["/path/to/project1", "/path/to/project2"]`
- Lock files:
  - `/path/to/project1/.file_watcher.lock`
  - `/path/to/project2/.file_watcher.lock`
- **NOT** in subdirectories like `/path/to/project1/src/.file_watcher.lock`

**Format** (JSON):
```json
{
  "pid": 12345,
  "timestamp": 1703567890.123,
  "worker_name": "file_watcher_worker",
  "hostname": "server1"
}
```

**Lock Acquisition**:
1. For each root watched directory from config
2. Check if `.lock` file exists in that root directory
3. If exists, check if process is alive (by PID)
4. If process dead, remove stale lock
5. Create new lock file atomically in root directory
6. Write lock info

**Lock Release**:
1. Remove `.lock` file from root watched directory
2. Handle cleanup on process exit

## Queue Mechanism for Changed Files

### Recommended Approach: Direct Database Marking

**Strategy**: Mark files as needing processing directly in database.

**Flow**:
1. File watcher detects change
2. Update `last_modified` in `files` table
3. Call `mark_file_needs_chunking()` (deletes existing chunks)
4. Vectorization worker picks up via `get_files_needing_chunking()`

**Pros**:
- Simple and reliable
- No additional queue infrastructure
- Leverages existing mechanism
- Atomic operations

**Alternative**: Use existing queue manager (if needed for more complex workflows)

## Process Architecture

### File Watcher Process

```python
# code_analysis/core/file_watcher_pkg/runner.py

def run_file_watcher_worker(
    db_path: str,
    project_id: str,
    watch_dirs: List[str],
    scan_interval: int = 60,
    worker_log_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run file watcher worker in separate process.
    
    Similar structure to vectorization worker runner.
    """
    # Setup logging
    _setup_worker_logging(worker_log_path)
    
    # Initialize database
    database = CodeDatabase(Path(db_path))
    
    # Create worker
    worker = FileWatcherWorker(
        db_path=Path(db_path),
        project_id=project_id,
        watch_dirs=[Path(d) for d in watch_dirs],
        scan_interval=scan_interval,
    )
    
    # Run worker
    try:
        result = asyncio.run(worker.run())
        return result
    except KeyboardInterrupt:
        worker.stop()
        return {"scanned": 0, "errors": 0, "interrupted": True}
    finally:
        database.close()
```

### Integration in main.py

```python
# In startup_vectorization_worker() or separate function

async def startup_file_watcher_worker() -> None:
    """Start file watcher worker in background process."""
    import multiprocessing
    from code_analysis.core.file_watcher_pkg import run_file_watcher_worker
    
    # Get config
    worker_config = server_config.file_watcher
    
    if not worker_config.get("enabled", True):
        return
    
    watch_dirs = worker_config.get("watch_dirs", [])
    if not watch_dirs:
        return
    
    # Start process
    process = multiprocessing.Process(
        target=run_file_watcher_worker,
        args=(
            str(db_path),
            project_id,
            watch_dirs,
        ),
        kwargs={
            "scan_interval": worker_config.get("scan_interval", 60),
            "worker_log_path": worker_config.get("log_path"),
        },
        daemon=True,
    )
    process.start()
    logger.info(f"File watcher worker started with PID {process.pid}")
```

## Configuration Schema

```json
{
  "code_analysis": {
    "file_watcher": {
      "enabled": true,
      "scan_interval": 60,
      "lock_file_name": ".file_watcher.lock",
      "watch_dirs": [
        "/path/to/project1",
        "/path/to/project2"
      ],
      "log_path": "logs/file_watcher.log",
      "version_dir": "data/versions",
      "max_scan_duration": 300,
      "ignore_patterns": [
        "**/__pycache__/**",
        "**/.git/**",
        "**/node_modules/**"
      ]
    }
  }
}
```

**Version Directory**:
- Default: `data/versions/`
- Structure: `{version_dir}/{project_id}/{relative_path}`
- Example: `data/versions/{project_id}/src/module.py`
- Original path is stored in `original_path` column

## Error Handling

1. **Lock file errors** (cannot create lock):
   - Log error with details
   - Skip this root directory for this cycle
   - Continue to next root directory
   - Do NOT stop worker

2. **Database errors**:
   - Log error with details
   - Continue with next root directory
   - Do NOT stop worker

3. **File system errors** (permission denied, etc.):
   - Log error for specific file/directory
   - Continue scanning other files/directories
   - Do NOT stop worker

4. **Process crashes**:
   - Lock file cleanup on next scan (in root directory)
   - Stale locks detected by checking if PID process is alive

5. **Subdirectory errors**:
   - Log but continue scanning other subdirectories
   - Do NOT stop scanning of root directory

**General rule**: Log error and continue to next step/directory. Only stop on critical errors (database connection lost, etc.).

## Performance Considerations

1. **Scan interval**: Default 60 seconds (configurable)
2. **Batch processing**: Process multiple files in one transaction
3. **Index usage**: Ensure indexes on `last_modified`, `deleted`, `path`
4. **Lock file checks**: Only check PID, not full process info

## Testing Strategy

1. **Unit tests**: Lock manager, scanner, processor
2. **Integration tests**: Full worker cycle
3. **Stress tests**: Many files, rapid changes
4. **Lock tests**: Multiple processes, stale locks

## Migration Path

1. **Phase 1**: Add `deleted` column (backward compatible)
2. **Phase 2**: Deploy file watcher (can be disabled)
3. **Phase 3**: Enable file watcher
4. **Phase 4**: Add cleanup commands
5. **Phase 5**: Add version collapse

## Summary

This architecture provides:
- ✅ Soft delete with `deleted` flag
- ✅ File movement to version directory on deletion
- ✅ File restoration from version directory on unmark
- ✅ `original_path` and `version_dir` columns for path tracking
- ✅ Cleanup commands for deleted files (hard delete with physical file removal)
- ✅ Unmark deleted file command (restore from version directory)
- ✅ Version collapse functionality
- ✅ Parallel file watcher process
- ✅ Lock file mechanism for process safety
- ✅ Efficient change detection via mtime comparison
- ✅ Integration with existing vectorization worker

The design is modular, testable, and follows existing patterns in the codebase.

