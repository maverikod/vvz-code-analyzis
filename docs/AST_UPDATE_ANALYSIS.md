# AST Update Analysis: How AST Nodes Are Saved and Updated

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-01-27

## Executive Summary

This document analyzes how AST (Abstract Syntax Tree) nodes are saved to the database and whether the AST tree is automatically updated after CST (Concrete Syntax Tree) editing operations.

**Key Finding**: ❌ **AST tree is NOT automatically updated after CST editing**. The AST tree is only updated when `update_indexes` command is explicitly called.

## 1. How AST Nodes Are Saved to Database

### 1.1 AST Storage Process

AST nodes are saved to the database through the `update_indexes` command (`code_analysis/commands/code_mapper_mcp_command.py`).

**Process Flow**:

```255:280:code_analysis/commands/code_mapper_mcp_command.py
            try:
                # Use parse_with_comments to preserve comments in AST
                from ..core.ast_utils import parse_with_comments
                tree = parse_with_comments(file_content, filename=str(file_path))
            except SyntaxError as e:
                logger.warning(f"Syntax error in {rel_path}: {e}")
                return {"file": rel_path, "status": "syntax_error", "error": str(e)}

            import hashlib

            ast_json = json.dumps(ast.dump(tree))
            ast_hash = hashlib.sha256(ast_json.encode()).hexdigest()

            try:
                # NOTE: save_ast_tree is intentionally synchronous. We must not create
                # nested event loops inside queue workers / async contexts.
                logger.debug(f"Saving AST for {rel_path}, file_id={file_id}, project_id={project_id}")
                ast_tree_id = database.save_ast_tree(
                    file_id,
                    project_id,
                    ast_json,
                    ast_hash,
                    file_mtime,
                    overwrite=True,
                )
                logger.debug(f"AST saved with id={ast_tree_id} for file_id={file_id}")
```

**Steps**:
1. **Parse file content with comments preserved** → `parse_with_comments(file_content, filename=str(file_path))`
   - Uses `code_analysis/core/ast_utils.py::parse_with_comments()` utility
   - Comments are preserved as `ast.Expr(ast.Constant(value="# comment"))` nodes
   - Comments are inserted before the statements they precede
2. **Serialize AST** → `json.dumps(ast.dump(tree))`
3. **Calculate hash** → `hashlib.sha256(ast_json.encode()).hexdigest()`
4. **Save to database** → `database.save_ast_tree(...)`

**Note**: AST now preserves comments using the `parse_with_comments()` utility function. Comments are stored as expression nodes in the AST, allowing them to be restored when needed. This enhancement was added in Phase 5 of the unified implementation plan.

### 1.2 Database Schema

AST trees are stored in the `ast_trees` table:

```396:409:code_analysis/core/database/base.py
                CREATE TABLE IF NOT EXISTS ast_trees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    project_id TEXT NOT NULL,
                    ast_json TEXT NOT NULL,
                    ast_hash TEXT NOT NULL,
                    file_mtime REAL NOT NULL,
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now')),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    UNIQUE(file_id, ast_hash)
                )
```

**Key Fields**:
- `ast_json`: Full AST serialized as JSON (includes comments as expression nodes)
- `ast_hash`: SHA256 hash of AST for change detection
- `file_mtime`: File modification time (used for synchronization)
- `UNIQUE(file_id, ast_hash)`: Prevents duplicate AST trees for the same file

**Comment Preservation**:
- Comments are preserved in AST using `parse_with_comments()` utility (`code_analysis/core/ast_utils.py`)
- Comments are stored as `ast.Expr(ast.Constant(value="# comment"))` nodes
- Comments maintain their position relative to code statements
- This allows AST-based file restoration with comments preserved
- Enhancement added in Phase 5 of the unified implementation plan

### 1.3 When AST Is Saved

AST is saved in the following scenarios:

1. **Explicit `update_indexes` command call**:
   - User manually calls `update_indexes` via MCP
   - Command processes all files in project or specific files
   - For each file: parses AST → saves to database

2. **Initial project indexing**:
   - When project is first added to database
   - `update_indexes` is called to build initial index

3. **File analysis during indexing**:
   - `_analyze_file()` method processes each file
   - AST is parsed and saved with `overwrite=True`

## 2. CST Editing and AST Update

### 2.1 CST Editing Process

CST editing is performed through `compose_cst_module` command (`code_analysis/commands/cst_compose_module_command.py`).

**Process Flow**:

```435:447:code_analysis/commands/cst_compose_module_command.py
            if apply:
                backup_path = write_with_backup(
                    target, new_source, create_backup=create_backup
                )
                
                # Create git commit if git repository and commit_message provided
                if is_git and commit_message:
                    git_commit_success, git_error = create_git_commit(
                        root_path, target, commit_message
                    )
                    if not git_commit_success:
                        logger.warning(f"Failed to create git commit: {git_error}")
```

**Steps**:
1. **Apply CST operations** → Modify code using CST transformers
2. **Validate** → Compile check, docstring validation
3. **Write to disk** → `write_with_backup(target, new_source, ...)`
4. **Git commit** (optional) → If `commit_message` provided

### 2.2 ✅ AST Is Now Updated After CST Editing

**Status**: After CST editing, the AST tree in the database is **automatically updated** via `update_file_data()`.

**Implementation** (Phase 3 of unified implementation plan):
- `compose_cst_module` command now calls `update_file_data()` after writing file to disk
- `update_file_data()` clears old records and recreates them via `_analyze_file()`
- `_analyze_file()` parses AST with comments preserved and saves to database
- AST tree is kept in sync with file content automatically

**Code Location**:
```448:487:code_analysis/commands/cst_compose_module_command.py
                # Update database after file write
                try:
                    database = self._open_database(str(root_path), auto_analyze=False)
                    try:
                        project_id = self._get_project_id(
                            database, root_path, kwargs.get("project_id")
                        )
                        if project_id:
                            # Get relative path for update_file_data
                            try:
                                rel_path = str(target.relative_to(root_path))
                            except ValueError:
                                # File is outside root, use absolute path
                                rel_path = str(target)
                            
                            update_result = database.update_file_data(
                                file_path=rel_path,
                                project_id=project_id,
                                root_dir=root_path,
                            )
                            if not update_result.get("success"):
                                logger.warning(
                                    f"Failed to update database after CST compose: "
                                    f"{update_result.get('error')}"
                                )
                            else:
                                logger.info(
                                    f"Database updated after CST compose: "
                                    f"AST={update_result.get('ast_updated')}, "
                                    f"CST={update_result.get('cst_updated')}, "
                                    f"entities={update_result.get('entities_updated')}"
                                )
                    finally:
                        database.close()
                except Exception as e:
                    logger.error(
                        f"Error updating database after CST compose: {e}",
                        exc_info=True,
                    )
                    # Don't fail the operation, just log the error
```

**Result**: AST tree in database is now automatically synchronized with file content after CST editing operations.

### 2.3 File Watcher Behavior

File watcher (`code_analysis/core/file_watcher_pkg/processor.py`) detects file changes and automatically updates database:

```611:637:code_analysis/core/file_watcher_pkg/processor.py
            # Update all database records for changed file
            update_result = self.database.update_file_data(
                file_path=file_path,
                project_id=project_id,
                root_dir=root_dir,
            )
            
            if update_result.get("success"):
                logger.debug(
                    f"[QUEUE] File updated in database: {file_path} | "
                    f"AST={update_result.get('ast_updated')}, "
                    f"CST={update_result.get('cst_updated')}"
                )
                
                # Mark for chunking (vectorization worker will process)
                # Note: Immediate vectorization is not done here because this is sync context
                # Worker will handle vectorization in background
                self.database.mark_file_needs_chunking(file_path, project_id)
                logger.debug(f"[QUEUE] File marked for worker vectorization: {file_path}")
                
                return True
            else:
                logger.error(
                    f"[QUEUE] Failed to update file in database: {file_path} | "
                    f"Error: {update_result.get('error')}"
                )
                return False
```

**What File Watcher Does** (Phase 4 of unified implementation plan):
- ✅ Detects file changes (compares `mtime` with `last_modified`)
- ✅ **Updates AST tree** via `update_file_data()`
- ✅ **Updates CST tree** via `update_file_data()`
- ✅ **Updates code entities** (classes, functions, methods) via `update_file_data()`
- ✅ Marks file for chunking (`mark_file_needs_chunking`)
- ✅ Updates `last_modified` timestamp

**Result**: File watcher now automatically keeps AST/CST/entities in sync with file changes.
- ❌ Does NOT parse AST
- ❌ Does NOT save AST to database

## 3. Impact Analysis

### 3.1 Problems Caused by Stale AST

1. **Outdated AST in Database**:
   - AST tree in `ast_trees` table reflects old code structure
   - New classes/functions/methods added via CST are not in AST
   - Deleted code still appears in AST

2. **Inconsistent Analysis Results**:
   - `get_ast` command returns outdated AST
   - `search_ast_nodes` searches old structure
   - `ast_statistics` shows incorrect counts

3. **Vectorization Issues**:
   - Chunks may reference non-existent AST nodes
   - AST bindings (`class_id`, `function_id`, `method_id`) may be invalid
   - Vectorization worker may fail on stale AST references

4. **Code Entity Information**:
   - `get_code_entity_info` may return outdated information
   - Entity relationships may be incorrect

### 3.2 When AST Becomes Stale

AST becomes stale in these scenarios:

1. **After CST editing**:
   - User edits code via `compose_cst_module`
   - File is written to disk
   - AST in database is NOT updated
   - **User must manually call `update_indexes`**

2. **After direct file editing**:
   - User edits file directly (outside CST tools)
   - File watcher detects change
   - File is marked for chunking
   - **AST is NOT updated automatically**

3. **After external tools**:
   - Code formatters (black, autopep8)
   - IDE refactoring tools
   - Git merge/rebase operations
   - **AST is NOT updated automatically**

## 4. Current Workflow

### 4.1 Recommended Workflow

**After CST Editing**:
1. ✅ Edit code via `compose_cst_module`
2. ✅ File is written to disk
3. ⚠️ **Manually call `update_indexes`** to update AST
4. ✅ AST is now synchronized with file

**Example**:
```python
# Step 1: Edit code via CST
compose_cst_module(
    root_dir="/path",
    file_path="file.py",
    ops=[...],
    apply=True
)

# Step 2: Update AST (REQUIRED)
update_indexes(
    root_dir="/path",
    file_path="file.py"  # Optional: specific file
)
```

### 4.2 Automatic Update Options

**Option 1: Add AST Update to `compose_cst_module`** (Recommended)
- After successful file write, automatically call `update_indexes` for edited file
- Ensures AST is always synchronized
- May add latency to CST editing operation

**Option 2: File Watcher Triggers AST Update**
- File watcher detects change
- Automatically calls `update_indexes` for changed file
- Requires file watcher to be running
- May process files in background (async)

**Option 3: Lazy AST Update**
- AST is updated on-demand when accessed
- Check `file_mtime` vs AST `file_mtime`
- If outdated, parse and update AST before returning
- Adds latency to AST queries

## 5. Recommendations

### 5.1 Immediate Actions

1. **Document the Limitation**:
   - Add warning to `compose_cst_module` documentation
   - Inform users that AST update is required after CST editing

2. **Add AST Update to CST Command** (Recommended):
   - After successful file write in `compose_cst_module`
   - Automatically call `update_indexes` for edited file
   - Make it optional via parameter (default: `True`)

3. **Add AST Update to File Watcher**:
   - When file watcher detects change
   - Queue file for AST update (not just chunking)
   - Process AST updates in background

### 5.2 Long-Term Improvements

1. **Unified Update Mechanism**:
   - Single command/worker that updates:
     - File metadata
     - AST tree
     - CST tree
     - Code chunks
   - Ensures consistency across all data structures

2. **AST Versioning**:
   - Track AST versions with file versions
   - Detect stale AST automatically
   - Auto-update on access if stale

3. **Incremental AST Updates**:
   - Only update changed parts of AST
   - Faster updates for large files
   - Better performance

## 6. Code References

### 6.1 AST Saving

- **Command**: `code_analysis/commands/code_mapper_mcp_command.py`
- **Method**: `_analyze_file()` (lines 127-277)
- **Database**: `database.save_ast_tree()` (called at line 246)

### 6.2 CST Editing

- **Command**: `code_analysis/commands/cst_compose_module_command.py`
- **Method**: `execute()` (lines 208-476)
- **File Write**: `write_with_backup()` (line 436)

### 6.3 File Watcher

- **Processor**: `code_analysis/core/file_watcher_pkg/processor.py`
- **Method**: `_queue_file_for_processing()` (lines 504-580)
- **Action**: Marks file for chunking, updates `last_modified`

## 7. Conclusion

**Current State**:
- ✅ AST is saved to database via `update_indexes` command
- ✅ CST editing successfully modifies files
- ❌ AST is NOT automatically updated after CST editing
- ❌ AST becomes stale after file changes

**Required Actions**:
1. Add automatic AST update to `compose_cst_module` (recommended)
2. Add AST update to file watcher processing
3. Document the limitation and workflow

**Impact**:
- Medium: AST queries return outdated data
- Medium: Vectorization may fail on stale AST references
- Low: Analysis results may be incorrect

**Priority**: **Medium** - Should be fixed to ensure data consistency.

