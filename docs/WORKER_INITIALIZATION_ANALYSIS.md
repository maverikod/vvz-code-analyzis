# Worker Initialization and Startup Analysis

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-10

## Executive Summary

This document provides a deep analysis of worker initialization and startup code, identifying logical duplications and architectural inconsistencies.

## 1. Critical Duplications Found

### 1.1 Config Loading Duplication

**Location**: `code_analysis/main.py`

Both `startup_vectorization_worker()` (lines 586-750) and `startup_file_watcher_worker()` (lines 752-901) contain **identical** config loading logic:

```python
# DUPLICATED IN BOTH FUNCTIONS (lines 606-625 and 769-788)
from mcp_proxy_adapter.config import get_config

cfg = get_config()
app_config = getattr(cfg, "config_data", {})
if not app_config:
    # Fallback: try to load from config_path
    if hasattr(cfg, "config_path") and cfg.config_path:
        import json
        with open(cfg.config_path, "r", encoding="utf-8") as f:
            app_config = json.load(f)

logger.info(f"🔍 app_config loaded: {bool(app_config)}, keys: {list(app_config.keys()) if app_config else []}")

# Check if code_analysis config section exists
code_analysis_config = app_config.get("code_analysis", {})
logger.info(f"🔍 code_analysis_config found: {bool(code_analysis_config)}")
if not code_analysis_config:
    logger.warning("⚠️  No code_analysis config found, skipping...")
    return

# Create ServerConfig
server_config = ServerConfig(**code_analysis_config)
```

**Impact**: 
- ~40 lines of duplicated code
- Maintenance burden: changes must be made in two places
- Risk of inconsistencies if one function is updated but not the other

**Recommendation**: Extract to helper function:
```python
def _load_worker_config() -> tuple[Optional[ServerConfig], Optional[dict]]:
    """Load and validate worker configuration.
    
    Returns:
        Tuple of (ServerConfig, code_analysis_config_dict) or (None, None) if invalid.
    """
    from mcp_proxy_adapter.config import get_config
    from code_analysis.core.config import ServerConfig
    
    cfg = get_config()
    app_config = getattr(cfg, "config_data", {})
    if not app_config:
        if hasattr(cfg, "config_path") and cfg.config_path:
            import json
            with open(cfg.config_path, "r", encoding="utf-8") as f:
                app_config = json.load(f)
    
    code_analysis_config = app_config.get("code_analysis", {})
    if not code_analysis_config:
        return None, None
    
    try:
        server_config = ServerConfig(**code_analysis_config)
        return server_config, code_analysis_config
    except Exception as e:
        logger.error(f"Failed to create ServerConfig: {e}", exc_info=True)
        return None, None
```

### 1.2 Storage Path Resolution Duplication

**Location**: `code_analysis/main.py`

Both functions resolve storage paths identically:

```python
# DUPLICATED IN BOTH FUNCTIONS (lines 649-656 and 820-826)
config_path = BaseMCPCommand._resolve_config_path()
config_data = load_raw_config(config_path)
storage = resolve_storage_paths(
    config_data=config_data, config_path=config_path
)
db_path = storage.db_path
```

**Impact**: 
- ~7 lines duplicated
- Same pattern repeated

**Recommendation**: Extract to helper:
```python
def _resolve_worker_storage() -> StoragePaths:
    """Resolve storage paths for workers.
    
    Returns:
        StoragePaths object.
    """
    from code_analysis.commands.base_mcp_command import BaseMCPCommand
    from code_analysis.core.storage_paths import load_raw_config, resolve_storage_paths
    
    config_path = BaseMCPCommand._resolve_config_path()
    config_data = load_raw_config(config_path)
    return resolve_storage_paths(config_data=config_data, config_path=config_path)
```

### 1.3 Worker Launch Inconsistency

**Location**: `code_analysis/main.py` vs `code_analysis/core/worker_launcher.py`

**Problem**: 
- `startup_file_watcher_worker()` launches worker **directly** via `multiprocessing.Process` (lines 868-883)
- `startup_vectorization_worker()` uses `worker_launcher.start_vectorization_worker()` (line 723)
- `worker_launcher.py` has `start_file_watcher_worker()` function (lines 41-96) that is **NOT USED** in `main.py`

**Impact**:
- Inconsistent architecture
- File watcher bypasses `WorkerManager` registration (though it's done manually later)
- Code duplication: `worker_launcher.start_file_watcher_worker()` duplicates logic from `main.py`

**Current State**:
```python
# main.py - file watcher (lines 868-883)
process = multiprocessing.Process(
    target=run_file_watcher_worker,
    args=(str(db_path), valid_watch_dirs),
    kwargs={...},
    daemon=True,
)
process.start()
# Manual PID file writing (lines 894-899)

# main.py - vectorization (line 723)
result = start_vectorization_worker(...)  # Uses worker_launcher

# worker_launcher.py - has unused function
def start_file_watcher_worker(...) -> WorkerStartResult:
    # Similar logic but not used!
```

**Recommendation**: 
1. Use `worker_launcher.start_file_watcher_worker()` in `main.py` for consistency
2. Remove direct `multiprocessing.Process` creation from `main.py`
3. Ensure both workers go through same launch path

### 1.4 Enabled Check Pattern Duplication

**Location**: `code_analysis/main.py`

Both functions check if worker is enabled, but with different patterns:

```python
# Vectorization worker (lines 641-647)
worker_config = server_config.worker
if worker_config and isinstance(worker_config, dict):
    if not worker_config.get("enabled", True):
        logger.info("ℹ️  Vectorization worker is disabled in config, skipping")
        return

# File watcher worker (lines 797-806)
file_watcher_config = server_config.file_watcher
if not file_watcher_config or not isinstance(file_watcher_config, dict):
    logger.info("ℹ️  No file_watcher config found, skipping file watcher worker")
    return

if not file_watcher_config.get("enabled", True):
    logger.info("ℹ️  File watcher worker is disabled in config, skipping")
    return
```

**Impact**: 
- Similar logic but different structure
- Could be unified

**Recommendation**: Extract helper:
```python
def _is_worker_enabled(config_section: Optional[dict], worker_name: str) -> bool:
    """Check if worker is enabled in config.
    
    Args:
        config_section: Worker config section (worker or file_watcher).
        worker_name: Worker name for logging.
    
    Returns:
        True if enabled, False otherwise.
    """
    if not config_section or not isinstance(config_section, dict):
        logger.info(f"ℹ️  No {worker_name} config found, skipping")
        return False
    
    if not config_section.get("enabled", True):
        logger.info(f"ℹ️  {worker_name} worker is disabled in config, skipping")
        return False
    
    return True
```

### 1.5 Database Creation Logic

**Location**: `code_analysis/main.py`

Only `startup_vectorization_worker()` contains database auto-creation logic (lines 658-683). This logic is **missing** from `startup_file_watcher_worker()`, which also needs database access.

**Impact**:
- Inconsistency: file watcher may fail if database doesn't exist
- Logic should be shared or both should handle it

**Recommendation**: Extract to shared helper:
```python
def _ensure_database_exists(db_path: Path) -> None:
    """Ensure database file exists, create if missing.
    
    Args:
        db_path: Path to database file.
    """
    if db_path.exists():
        return
    
    logger.info(f"Database file not found, creating new database at {db_path}")
    try:
        from code_analysis.core.database import CodeDatabase
        from code_analysis.core.database.base import create_driver_config_for_worker
        
        db_path.parent.mkdir(parents=True, exist_ok=True)
        driver_config = create_driver_config_for_worker(
            db_path=db_path,
            driver_type="sqlite_proxy",
        )
        init_database = CodeDatabase(driver_config=driver_config)
        init_database.close()
        logger.info(f"Created new database at {db_path}")
    except Exception as e:
        logger.warning(f"Failed to create database: {e}, continuing anyway", exc_info=True)
```

## 2. Architectural Issues

### 2.1 Mixed Launch Patterns

**Problem**: Two different patterns for launching workers:
1. Direct `multiprocessing.Process` (file watcher in main.py)
2. Via `worker_launcher` functions (vectorization)

**Recommendation**: Unify to use `worker_launcher` for both.

### 2.2 PID File Management Inconsistency

**Problem**:
- File watcher: PID file written in `main.py` (lines 894-899)
- Vectorization: PID file written in `worker_launcher.start_vectorization_worker()` (lines 175-180)
- Different locations and error handling

**Recommendation**: Centralize PID file management in `worker_launcher`.

### 2.3 Error Handling Duplication

Both functions have identical error handling patterns:

```python
# DUPLICATED IN BOTH
except Exception as e:
    print(f"❌ Failed to start {worker} worker: {e}", flush=True, file=sys.stderr)
    logger.error(f"❌ Failed to start {worker} worker: {e}", exc_info=True)
```

**Recommendation**: Extract to helper or use decorator.

## 3. Code Metrics

### Duplication Statistics

| Category | Lines Duplicated | Functions Affected |
|----------|------------------|-------------------|
| Config Loading | ~40 | 2 |
| Storage Resolution | ~7 | 2 |
| Enabled Checks | ~15 | 2 |
| Error Handling | ~6 | 2 |
| **Total** | **~68** | **2** |

### Refactoring Impact

**Estimated reduction**: ~68 lines of duplicated code can be extracted to ~100 lines of shared helpers (net reduction: ~36 lines, but with better maintainability).

## 4. Recommended Refactoring

### 4.1 Create Worker Startup Helper Module

**New file**: `code_analysis/core/worker_startup_helpers.py`

```python
"""Helper functions for worker startup initialization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Optional, Tuple

from ..core.config import ServerConfig
from ..core.storage_paths import StoragePaths, load_raw_config, resolve_storage_paths
from ...commands.base_mcp_command import BaseMCPCommand


def load_worker_config() -> Tuple[Optional[ServerConfig], Optional[dict]]:
    """Load and validate worker configuration."""
    # ... (implementation from recommendation 1.1)


def resolve_worker_storage() -> StoragePaths:
    """Resolve storage paths for workers."""
    # ... (implementation from recommendation 1.2)


def is_worker_enabled(config_section: Optional[dict], worker_name: str) -> bool:
    """Check if worker is enabled in config."""
    # ... (implementation from recommendation 1.4)


def ensure_database_exists(db_path: Path) -> None:
    """Ensure database file exists, create if missing."""
    # ... (implementation from recommendation 1.5)
```

### 4.2 Refactor `startup_vectorization_worker()`

```python
async def startup_vectorization_worker() -> None:
    """Start universal vectorization worker in background process."""
    from code_analysis.core.worker_startup_helpers import (
        load_worker_config,
        resolve_worker_storage,
        is_worker_enabled,
        ensure_database_exists,
    )
    from code_analysis.core.worker_launcher import start_vectorization_worker
    
    logger = logging.getLogger(__name__)
    logger.info("🔍 startup_vectorization_worker called")
    
    try:
        # Load config (shared helper)
        server_config, code_analysis_config = load_worker_config()
        if not server_config:
            return
        
        # Check if chunker is configured
        if not server_config.chunker:
            logger.warning("⚠️  No chunker config found, skipping vectorization worker")
            return
        
        # Check if enabled (shared helper)
        worker_config = server_config.worker
        if not is_worker_enabled(worker_config, "vectorization"):
            return
        
        # Resolve storage (shared helper)
        storage = resolve_worker_storage()
        db_path = storage.db_path
        faiss_dir = storage.faiss_dir
        
        # Ensure database exists (shared helper)
        ensure_database_exists(Path(db_path))
        
        # ... (rest of function using helpers)
        
    except Exception as e:
        logger.error(f"❌ Failed to start vectorization worker: {e}", exc_info=True)
        print(f"❌ Failed to start vectorization worker: {e}", flush=True, file=sys.stderr)
```

### 4.3 Refactor `startup_file_watcher_worker()`

```python
async def startup_file_watcher_worker() -> None:
    """Start file watcher worker in background process."""
    from code_analysis.core.worker_startup_helpers import (
        load_worker_config,
        resolve_worker_storage,
        is_worker_enabled,
        ensure_database_exists,
    )
    from code_analysis.core.worker_launcher import start_file_watcher_worker
    
    logger = logging.getLogger(__name__)
    logger.info("🔍 startup_file_watcher_worker called")
    
    try:
        # Load config (shared helper)
        server_config, code_analysis_config = load_worker_config()
        if not server_config:
            return
        
        # Check if enabled (shared helper)
        file_watcher_config = server_config.file_watcher
        if not is_worker_enabled(file_watcher_config, "file_watcher"):
            return
        
        # Get watch_dirs
        worker_config = server_config.worker
        watch_dirs: list[str] = []
        if worker_config and isinstance(worker_config, dict):
            watch_dirs = worker_config.get("watch_dirs", [])
        
        if not watch_dirs:
            logger.warning("⚠️  No watch_dirs configured, skipping file watcher worker")
            return
        
        # Validate watch_dirs
        valid_watch_dirs: list[str] = []
        for watch_dir in watch_dirs:
            watch_dir_path = Path(watch_dir).resolve()
            if not watch_dir_path.exists():
                logger.warning(f"⚠️  Watch directory does not exist: {watch_dir_path}, skipping")
                continue
            valid_watch_dirs.append(str(watch_dir_path))
        
        if not valid_watch_dirs:
            logger.warning("⚠️  No valid watch directories found, skipping file watcher worker")
            return
        
        # Resolve storage (shared helper)
        storage = resolve_worker_storage()
        db_path = storage.db_path
        locks_dir = storage.locks_dir
        ensure_storage_dirs(storage)
        
        # Ensure database exists (shared helper)
        ensure_database_exists(Path(db_path))
        
        # Use worker_launcher for consistency
        scan_interval = file_watcher_config.get("scan_interval", 60)
        version_dir = file_watcher_config.get("version_dir", "data/versions")
        worker_log_path = file_watcher_config.get("log_path")
        ignore_patterns = file_watcher_config.get("ignore_patterns", [])
        
        result = start_file_watcher_worker(
            db_path=str(db_path),
            watch_dirs=valid_watch_dirs,
            locks_dir=str(locks_dir),
            scan_interval=scan_interval,
            version_dir=version_dir,
            worker_log_path=worker_log_path,
            ignore_patterns=ignore_patterns,
        )
        
        if result.success:
            logger.info(f"✅ File watcher worker started: {result.message}")
            print(f"✅ {result.message}", flush=True)
        else:
            logger.warning(f"⚠️  Failed to start file watcher worker: {result.message}")
            print(f"⚠️  {result.message}", flush=True)
        
    except Exception as e:
        logger.error(f"❌ Failed to start file watcher worker: {e}", exc_info=True)
        print(f"❌ Failed to start file watcher worker: {e}", flush=True, file=sys.stderr)
```

## 5. Benefits of Refactoring

1. **Reduced Duplication**: ~68 lines of duplicated code eliminated
2. **Consistency**: Both workers use same initialization pattern
3. **Maintainability**: Changes to config loading/storage resolution in one place
4. **Testability**: Helper functions can be unit tested independently
5. **Architectural Clarity**: Clear separation of concerns

## 6. Implementation Priority

1. **High Priority**: Extract config loading and storage resolution (affects both workers)
2. **Medium Priority**: Unify worker launch pattern (use worker_launcher for both)
3. **Low Priority**: Extract enabled check and error handling helpers

## 7. Testing Considerations

After refactoring:
1. Test that both workers still start correctly
2. Test error handling paths
3. Test config validation edge cases
4. Test database creation logic
5. Integration tests for full startup flow
