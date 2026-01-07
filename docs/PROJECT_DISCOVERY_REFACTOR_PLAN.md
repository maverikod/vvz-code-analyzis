# Project Discovery Refactor Plan

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Overview

This document describes a refactoring plan to change how projects are discovered and associated with files in the code analysis system.

## Current Architecture

### Current Approach
1. **Configuration-based**: Projects are explicitly configured in `watch_dirs` with their `project_id`
2. **One-to-one mapping**: Each `watch_dir` corresponds to one project
3. **Pre-determined projects**: Project IDs are known before scanning starts
4. **File-to-project mapping**: Files are associated with projects based on which `watch_dir` they are scanned from

### Current Flow
```
config.json → watch_dirs: ["/path/to/project1", "/path/to/project2"]
  ↓
File Watcher → For each watch_dir:
  - Get project_id from config/DB
  - Scan directory recursively
  - Associate all files with that project_id
```

### Current Limitations
1. **Rigid structure**: Each watched directory must be a project root
2. **No nested projects**: Cannot have multiple projects within one watched directory
3. **Manual configuration**: Must explicitly configure each project
4. **Subdirectory projects**: Subdirectories of watched dirs are not recognized as separate projects

## New Architecture

### New Approach
1. **Discovery-based**: Projects are discovered automatically by finding `projectid` files
2. **One watched directory, multiple projects**: A single `watch_dir` can contain multiple projects
3. **Dynamic discovery**: Projects are discovered during scanning by walking up the directory tree
4. **File-to-project mapping**: Each file is associated with the nearest project (by finding `projectid` file)

### New Flow
```
config.json → watch_dirs: ["/home/user/projects"]
  ↓
File Watcher → Scan /home/user/projects recursively:
  - For each file found:
    1. Walk up directory tree from file
    2. Find nearest directory with projectid file
    3. Validate no nested projects (parent has projectid)
    4. Load project_id from projectid file
    5. Associate file with discovered project
```

### Key Requirements
1. **Single watched directory**: One `watch_dir` can contain multiple projects
2. **Project discovery**: Projects are identified by presence of `projectid` file (UUID4)
3. **No nested projects**: If both parent and child directories have `projectid`, it's an error
4. **Automatic association**: Files are automatically associated with the nearest project root

## Detailed Implementation Plan

### Phase 1: Project Discovery Module

#### 1.1 Create `project_discovery.py` Module

**Location**: `code_analysis/core/project_discovery.py`

**Purpose**: Core logic for discovering projects and associating files with projects.

**Functions to implement**:

```python
def find_project_root(file_path: Path, watch_dirs: List[Path]) -> Optional[ProjectRoot]:
    """
    Find the project root for a given file by walking up the directory tree.
    
    Algorithm:
    1. Start from file_path's parent directory
    2. Walk up the directory tree
    3. For each directory:
       a. Check if it's within any watch_dir
       b. Check if it contains projectid file
       c. If found, validate no nested projects
       d. Return ProjectRoot if valid
    
    Args:
        file_path: Path to file
        watch_dirs: List of watched directories (absolute paths)
    
    Returns:
        ProjectRoot if found, None otherwise
    
    Raises:
        NestedProjectError: If nested projects detected
    """
    pass

def validate_no_nested_projects(project_root: Path) -> None:
    """
    Validate that no parent directory contains a projectid file.
    
    Algorithm:
    1. Walk up from project_root to each watch_dir
    2. Check each parent directory for projectid file
    3. If found, raise NestedProjectError
    
    Args:
        project_root: Path to project root (contains projectid)
    
    Raises:
        NestedProjectError: If parent directory has projectid
    """
    pass

def discover_projects_in_directory(watch_dir: Path) -> List[ProjectRoot]:
    """
    Discover all projects within a watched directory.
    
    Algorithm:
    1. Scan watch_dir recursively for projectid files
    2. For each projectid found:
       a. Validate no nested projects
       b. Load project_id from projectid file
       c. Create ProjectRoot object
    3. Return list of discovered projects
    
    Args:
        watch_dir: Watched directory to scan
    
    Returns:
        List of ProjectRoot objects
    
    Raises:
        NestedProjectError: If nested projects detected
    """
    pass

@dataclass
class ProjectRoot:
    """Represents a discovered project root."""
    root_path: Path
    project_id: str
    watch_dir: Path  # The watch_dir that contains this project
```

**Error Classes**:
```python
class NestedProjectError(ValueError):
    """Raised when nested projects are detected."""
    def __init__(self, child_project: Path, parent_project: Path):
        self.child_project = child_project
        self.parent_project = parent_project
        super().__init__(
            f"Nested projects detected: {child_project} is inside {parent_project}"
        )
```

#### 1.2 Update `project_resolution.py`

**Changes needed**:
- Add function to find project root from file path
- Add validation for nested projects
- Keep existing `load_project_id()` function (still used by commands)

**New functions**:
```python
def find_project_root_for_file(
    file_path: Path, 
    watch_dirs: List[Path]
) -> Optional[Tuple[Path, str]]:
    """
    Find project root and project_id for a file.
    
    Returns:
        Tuple of (project_root_path, project_id) or None
    """
    pass
```

### Phase 2: File Watcher Refactoring

#### 2.1 Update `scanner.py`

**Current behavior**: 
- Scans directory recursively
- Returns files with absolute paths
- No project association

**New behavior**:
- Scan directory recursively
- For each file, discover its project root
- Return files with project association

**Changes**:
```python
def scan_directory(
    root_dir: Path,
    watch_dirs: List[Path],  # NEW: List of watched directories
    project_root: Optional[Path] = None,  # DEPRECATED: Will be removed
    ignore_patterns: Optional[List[str]] = None,
) -> Dict[str, Dict]:
    """
    Scan directory recursively for code files and discover projects.
    
    Returns:
        Dictionary mapping absolute file paths to file info with project:
        {
            "/absolute/path/to/file.py": {
                "path": Path("/absolute/path/to/file.py"),
                "mtime": 1234567890.0,
                "size": 1024,
                "project_root": Path("/project/root"),  # NEW
                "project_id": "uuid-here",  # NEW
            }
        }
    """
    # For each file found:
    #   1. Find project root using find_project_root()
    #   2. If no project found, skip file (log warning)
    #   3. Add project_root and project_id to file info
```

#### 2.2 Update `processor.py`

**Current behavior**:
- `FileChangeProcessor` is initialized with a single `project_id`
- All files are associated with that project_id

**New behavior**:
- `FileChangeProcessor` handles multiple projects
- Files are grouped by project_id during processing
- Each project is processed separately

**Changes**:

```python
class FileChangeProcessor:
    def __init__(
        self,
        database: Any,
        watch_dirs: List[Path],  # NEW: List of watched directories
        version_dir: Optional[str] = None,
    ):
        # Remove project_id parameter
        # Store watch_dirs for project discovery
    
    def compute_delta(
        self, root_dir: Path, scanned_files: Dict[str, Dict]
    ) -> Dict[str, FileDelta]:  # Changed: Returns dict by project_id
        """
        Compute file change delta grouped by project.
        
        Returns:
            Dictionary mapping project_id to FileDelta:
            {
                "project-id-1": FileDelta(new_files=[...], changed_files=[...], deleted_files=[...]),
                "project-id-2": FileDelta(...),
            }
        """
        # Group files by project_id
        # For each project, compute delta separately
        # Return dict of deltas
    
    def queue_changes(
        self, root_dir: Path, deltas: Dict[str, FileDelta]
    ) -> Dict[str, Any]:
        """
        Queue changes for all projects.
        
        Args:
            root_dir: Root watched directory
            deltas: Dictionary of FileDelta by project_id
        
        Returns:
            Aggregated statistics
        """
        # For each project_id:
        #   - Get or create project in DB
        #   - Process delta for that project
        #   - Update statistics
```

#### 2.3 Update `multi_project_worker.py`

**Current behavior**:
- Takes list of `ProjectWatchSpec` (pre-configured projects)
- Each spec has `project_id` and `watch_dirs`

**New behavior**:
- Takes list of `WatchDirSpec` (just watched directories)
- Discovers projects dynamically during scanning
- Creates project specs on-the-fly

**Changes**:

```python
@dataclass(frozen=True, slots=True)
class WatchDirSpec:  # NEW: Replaces ProjectWatchSpec
    """
    Watched directory specification.
    
    Attributes:
        watch_dir: Directory to scan for projects
    """
    watch_dir: Path

class MultiProjectFileWatcherWorker:
    def __init__(
        self,
        db_path: Path,
        watch_dirs: Sequence[WatchDirSpec],  # Changed: List of watch dirs, not projects
        locks_dir: Path,
        scan_interval: int = 60,
        version_dir: Optional[str] = None,
        ignore_patterns: Optional[List[str]] = None,
    ):
        # Store watch_dirs list
        # Remove projects list
    
    async def _scan_cycle(
        self, database: Any, processor: FileChangeProcessor  # Changed: Single processor
    ) -> Dict[str, Any]:
        """
        Scan all watched directories and discover projects.
        """
        # For each watch_dir:
        #   - Scan directory (files with project discovery)
        #   - Compute delta (grouped by project)
        #   - Queue changes (for all discovered projects)
    
    def _scan_watch_dir(
        self, watch_dir: Path, processor: FileChangeProcessor
    ) -> Dict[str, Any]:
        """
        Scan a single watched directory and process all discovered projects.
        """
        # 1. Scan directory (files include project_root and project_id)
        # 2. Compute delta (returns dict by project_id)
        # 3. Queue changes (processes all projects)
```

### Phase 3: Database Integration

#### 3.1 Project Auto-Creation

**Current behavior**:
- Projects must be created explicitly or via `get_or_create_project()`

**New behavior**:
- Projects are auto-created when discovered
- Project root_path is the directory containing `projectid`
- Project name is derived from directory name

**Changes in `processor.py`**:
```python
def queue_changes(...):
    # For each project_id in deltas:
    #   - Get project_root from first file in delta
    #   - Call database.get_or_create_project(project_root, project_id)
    #   - Process files for that project
```

#### 3.2 File Association

**Current behavior**:
- Files are associated with project_id from config
- Files have `project_id` and `dataset_id`

**New behavior**:
- Files are associated with discovered project_id
- `dataset_id` is still used for multi-root indexing within a project
- File paths are still absolute

**No schema changes needed** - existing schema supports this.

### Phase 4: Configuration Changes

#### 4.1 Update Config Schema

**Current**:
```json
{
  "code_analysis": {
    "worker": {
      "watch_dirs": [
        "/path/to/project1",
        "/path/to/project2"
      ]
    }
  }
}
```

**New**:
```json
{
  "code_analysis": {
    "worker": {
      "watch_dirs": [
        "/home/user/projects"  // Can contain multiple projects
      ]
    }
  }
}
```

#### 4.2 Update Config Loading

**Location**: `code_analysis/main.py` → `startup_file_watcher_worker()`

**Changes**:
```python
# OLD:
project_watch_dirs = []
for watch_dir in watch_dirs:
    project_id = get_or_create_project_for_dir(watch_dir)
    project_watch_dirs.append((project_id, watch_dir))

# NEW:
watch_dir_specs = [WatchDirSpec(Path(watch_dir)) for watch_dir in watch_dirs]
# Projects will be discovered during scanning
```

### Phase 5: Error Handling and Validation

#### 5.1 Nested Project Detection

**When to check**:
1. During project discovery (`discover_projects_in_directory`)
2. When finding project root for a file (`find_project_root`)

**Error handling**:
- Log error with details (child and parent project paths)
- Skip the nested project (don't process files in it)
- Continue with other projects
- Optionally: Add command to list nested project errors

#### 5.2 Missing Project Detection

**When**: File found but no `projectid` in parent tree

**Behavior**:
- Log warning
- Skip file (don't add to database)
- Continue processing other files

#### 5.3 Invalid Project ID

**When**: `projectid` file exists but contains invalid UUID4

**Behavior**:
- Log error
- Skip project (don't process files in it)
- Continue with other projects

### Phase 6: Command Updates

#### 6.1 Update `delete_unwatched_projects` Command

**Current logic**:
- Checks if project root_path is in watch_dirs (exact match or subdirectory)

**New logic**:
- Discover all projects in watch_dirs
- Compare discovered projects with projects in database
- Delete projects not in discovered list

**Implementation**:
```python
def execute(...):
    # 1. Discover all projects in watch_dirs
    discovered_projects = set()
    for watch_dir in watch_dirs:
        projects = discover_projects_in_directory(watch_dir)
        discovered_projects.update(p.project_id for p in projects)
    
    # 2. Get all projects from database
    all_projects = database.get_all_projects()
    
    # 3. Find unwatched projects
    unwatched = [
        p for p in all_projects 
        if p["id"] not in discovered_projects
    ]
    
    # 4. Delete unwatched projects
```

#### 6.2 Update Other Commands

**Commands that need updates**:
- `start_worker`: Remove project_id parameter (projects discovered automatically)
- `list_project_files`: May need to filter by discovered projects
- Commands that take `root_dir`: Should work with project root or any file in project

### Phase 7: Testing and Migration

#### 7.1 Unit Tests

**Test cases**:
1. **Project discovery**:
   - Single project in watch_dir
   - Multiple projects in watch_dir
   - Nested projects (should error)
   - File outside any project (should skip)
   - Invalid projectid file (should skip)

2. **File association**:
   - File in project root
   - File in subdirectory of project
   - File at different nesting levels

3. **Error handling**:
   - Nested projects detection
   - Missing projectid
   - Invalid UUID in projectid

#### 7.2 Integration Tests

**Test scenarios**:
1. Scan directory with multiple projects
2. Add new project (add projectid file)
3. Remove project (remove projectid file)
4. Move project to different location
5. Nested project error handling

#### 7.3 Migration Strategy

**Steps**:
1. **Backup**: Backup database before migration
2. **Update code**: Deploy new code with feature flag
3. **Test**: Test with non-production data
4. **Enable**: Enable feature flag
5. **Verify**: Verify projects are discovered correctly
6. **Cleanup**: Remove old project configurations if needed

**Feature flag**:
```python
# config.json
{
  "code_analysis": {
    "worker": {
      "use_project_discovery": true  // Feature flag
    }
  }
}
```

### Phase 8: Documentation Updates

#### 8.1 Update Architecture Docs

**Files to update**:
- `docs/FILE_WATCHER_ARCHITECTURE.md`
- `docs/FILE_WATCHER_ARCHITECTURE_ANALYSIS.md`

**Changes**:
- Document new project discovery mechanism
- Update diagrams
- Explain nested project validation

#### 8.2 Update User Documentation

**Files to update**:
- `docs/README.md`
- Configuration examples

**Changes**:
- Explain new watch_dirs behavior
- Document projectid file requirements
- Explain nested project restrictions

## Implementation Steps Summary

### Step 1: Core Discovery Module (Phase 1)
1. Create `code_analysis/core/project_discovery.py`
2. Implement `find_project_root()`
3. Implement `validate_no_nested_projects()`
4. Implement `discover_projects_in_directory()`
5. Add unit tests

### Step 2: Update Scanner (Phase 2.1)
1. Update `scan_directory()` to discover projects
2. Return files with project association
3. Update tests

### Step 3: Update Processor (Phase 2.2)
1. Refactor `FileChangeProcessor` to handle multiple projects
2. Update `compute_delta()` to return dict by project_id
3. Update `queue_changes()` to process multiple projects
4. Update tests

### Step 4: Update Worker (Phase 2.3)
1. Change `ProjectWatchSpec` to `WatchDirSpec`
2. Update `MultiProjectFileWatcherWorker` to use discovery
3. Update `_scan_cycle()` and `_scan_watch_dir()`
4. Update tests

### Step 5: Update Configuration (Phase 4)
1. Update config loading in `main.py`
2. Remove project_id from worker startup
3. Update tests

### Step 6: Update Commands (Phase 6)
1. Update `delete_unwatched_projects`
2. Update `start_worker` command
3. Update other affected commands
4. Update tests

### Step 7: Error Handling (Phase 5)
1. Implement nested project detection
2. Add logging and error reporting
3. Add command to list project discovery errors
4. Update tests

### Step 8: Testing (Phase 7)
1. Write comprehensive unit tests
2. Write integration tests
3. Test migration path
4. Update documentation

## Benefits

1. **Flexibility**: One watched directory can contain multiple projects
2. **Automatic discovery**: No need to manually configure each project
3. **Simplified configuration**: Just specify top-level directories to watch
4. **Better organization**: Projects can be organized in a directory structure
5. **Validation**: Prevents nested projects (common mistake)

## Risks and Mitigations

### Risk 1: Performance Impact
**Risk**: Walking up directory tree for each file could be slow

**Mitigation**:
- Cache project roots during scan
- Use pathlib for efficient path operations
- Limit depth of search (only up to watch_dir)

### Risk 2: Nested Projects
**Risk**: Users might accidentally create nested projects

**Mitigation**:
- Clear error messages
- Validation during discovery
- Documentation with examples

### Risk 3: Migration Complexity
**Risk**: Existing projects might not have projectid files

**Mitigation**:
- Feature flag for gradual rollout
- Migration script to create projectid files
- Backward compatibility mode

## Success Criteria

1. ✅ File watcher discovers projects automatically from `projectid` files
2. ✅ Multiple projects can exist in one watched directory
3. ✅ Nested projects are detected and rejected
4. ✅ Files are correctly associated with discovered projects
5. ✅ All existing functionality continues to work
6. ✅ Performance is acceptable (no significant slowdown)
7. ✅ Documentation is updated

## Timeline Estimate

- **Phase 1** (Discovery Module): 2-3 days
- **Phase 2** (File Watcher Refactoring): 3-4 days
- **Phase 3** (Database Integration): 1-2 days
- **Phase 4** (Configuration): 1 day
- **Phase 5** (Error Handling): 1-2 days
- **Phase 6** (Commands): 2-3 days
- **Phase 7** (Testing): 2-3 days
- **Phase 8** (Documentation): 1 day

**Total**: ~13-19 days

## Next Steps

1. Review and approve this plan
2. Create feature branch
3. Start with Phase 1 (Core Discovery Module)
4. Implement incrementally with tests
5. Review and merge

