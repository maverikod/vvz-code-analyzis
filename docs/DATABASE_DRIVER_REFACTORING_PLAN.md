# Step-by-Step Plan: Database Driver Architecture Refactoring

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-10  
**Status**: Implementation Plan

## Overview

This document provides a detailed step-by-step implementation plan for refactoring the database driver architecture to:
1. Eliminate code duplication in worker initialization
2. Implement unified database driver layer for multi-database support
3. Centralize worker management through a single manager
4. Ensure proper database initialization and file management

## Architecture Summary

**Target Chain**:
```
Command → UniversalDriver → CodeDatabase → SQLiteDriverProxy → DB Worker → SQLiteDriver
```

**Key Principles**:
- SQLiteDriver is ONLY used inside DB worker process
- Commands use SQLiteDriverProxy (never SQLiteDriver directly)
- UniversalDriver handles database initialization and file management
- All workers start through WorkerManager
- DBWorkerManager reads config and starts DB worker for SQLite

---

## Phase 1: Create UniversalDriver Layer

### Step 1.1: Create UniversalDriver Class Structure

**Goal**: Create the UniversalDriver class with basic structure and interface.

**Files to Create**:
- `code_analysis/core/database/universal_driver.py`

**Implementation**:
```python
"""
Universal database driver interface.

Provides unified API for all database types, handling initialization,
file management, and schema creation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, Optional
import logging

from ..database.base import CodeDatabase
from ..storage_paths import resolve_storage_paths, load_raw_config

logger = logging.getLogger(__name__)


class UniversalDriver:
    """Unified database driver interface for all database types."""
    
    def __init__(self, db_config: Dict[str, Any]):
        """
        Initialize universal driver.
        
        Args:
            db_config: Database configuration with 'type' and connection details
        """
        self.db_config = db_config
        self.db_type = db_config.get("type", "sqlite")
        self._database: Optional[CodeDatabase] = None
        self._initialized = False
    
    def ensure_database_exists(self) -> bool:
        """Ensure database file/connection exists, create if needed."""
        # Implementation
        pass
    
    def initialize_schema(self) -> None:
        """Initialize database schema if not exists."""
        # Implementation
        pass
    
    def get_database(self) -> CodeDatabase:
        """Get CodeDatabase instance for operations."""
        # Implementation
        pass
    
    def close(self) -> None:
        """Close database connection."""
        # Implementation
        pass
```

**Checklist**:
- [ ] File `code_analysis/core/database/universal_driver.py` created
- [ ] Class `UniversalDriver` defined with all methods
- [ ] Imports are correct
- [ ] Docstrings added to class and methods
- [ ] Type hints added

**Tests**:
```python
# tests/test_universal_driver.py

def test_universal_driver_init():
    """Test UniversalDriver initialization."""
    config = {"type": "sqlite", "path": "test.db"}
    driver = UniversalDriver(config)
    assert driver.db_type == "sqlite"
    assert driver._database is None
    assert not driver._initialized

def test_universal_driver_init_invalid_config():
    """Test UniversalDriver with invalid config."""
    with pytest.raises(ValueError):
        UniversalDriver({})
```

---

### Step 1.2: Implement Database Type Detection

**Goal**: Add logic to detect database type from config and validate configuration.

**Implementation**:
```python
def _detect_db_type(self, config: Dict[str, Any]) -> str:
    """
    Detect database type from configuration.
    
    Args:
        config: Database configuration
        
    Returns:
        Database type string (sqlite, mysql, postgresql, etc.)
    """
    db_type = config.get("type", "sqlite")
    if db_type not in ["sqlite", "mysql", "postgresql"]:
        raise ValueError(f"Unsupported database type: {db_type}")
    return db_type

def _validate_config(self, config: Dict[str, Any]) -> None:
    """Validate database configuration."""
    if not config:
        raise ValueError("Database configuration is required")
    
    db_type = self._detect_db_type(config)
    
    if db_type == "sqlite":
        if "path" not in config:
            raise ValueError("SQLite requires 'path' in config")
    elif db_type in ["mysql", "postgresql"]:
        required = ["host", "database"]
        missing = [k for k in required if k not in config]
        if missing:
            raise ValueError(f"{db_type} requires: {', '.join(missing)}")
```

**Checklist**:
- [ ] `_detect_db_type()` method implemented
- [ ] `_validate_config()` method implemented
- [ ] SQLite config validation works
- [ ] MySQL/PostgreSQL config validation works (for future)
- [ ] Error messages are clear

**Tests**:
```python
def test_detect_db_type_sqlite():
    """Test SQLite type detection."""
    config = {"type": "sqlite", "path": "test.db"}
    driver = UniversalDriver(config)
    assert driver.db_type == "sqlite"

def test_detect_db_type_default():
    """Test default type (SQLite)."""
    config = {"path": "test.db"}
    driver = UniversalDriver(config)
    assert driver.db_type == "sqlite"

def test_validate_config_sqlite_missing_path():
    """Test SQLite validation without path."""
    config = {"type": "sqlite"}
    with pytest.raises(ValueError, match="path"):
        UniversalDriver(config)

def test_validate_config_unsupported_type():
    """Test unsupported database type."""
    config = {"type": "oracle"}
    with pytest.raises(ValueError, match="Unsupported"):
        UniversalDriver(config)
```

---

### Step 1.3: Implement Database File Existence Check

**Goal**: Add logic to check if database file exists (for SQLite) and create if needed.

**Implementation**:
```python
def ensure_database_exists(self) -> bool:
    """
    Ensure database file/connection exists, create if needed.
    
    For SQLite: Creates database file if it doesn't exist.
    For server DBs: Tests connection (future implementation).
    
    Returns:
        True if database exists or was created, False otherwise
    """
    if self.db_type == "sqlite":
        db_path = Path(self.db_config["path"])
        
        if db_path.exists():
            logger.debug(f"Database file exists: {db_path}")
            return True
        
        # Create parent directory if needed
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create empty database file
        try:
            # Touch file to create it
            db_path.touch()
            logger.info(f"Created database file: {db_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create database file: {e}", exc_info=True)
            return False
    else:
        # For server databases, test connection (future)
        logger.warning(f"Database existence check not implemented for {self.db_type}")
        return True
```

**Checklist**:
- [ ] `ensure_database_exists()` implemented for SQLite
- [ ] Parent directory creation works
- [ ] File creation works
- [ ] Error handling for file creation
- [ ] Logging added

**Tests**:
```python
def test_ensure_database_exists_creates_file(tmp_path):
    """Test database file creation."""
    db_path = tmp_path / "test.db"
    config = {"type": "sqlite", "path": str(db_path)}
    driver = UniversalDriver(config)
    
    result = driver.ensure_database_exists()
    assert result is True
    assert db_path.exists()

def test_ensure_database_exists_creates_parent_dir(tmp_path):
    """Test parent directory creation."""
    db_path = tmp_path / "subdir" / "test.db"
    config = {"type": "sqlite", "path": str(db_path)}
    driver = UniversalDriver(config)
    
    result = driver.ensure_database_exists()
    assert result is True
    assert db_path.parent.exists()
    assert db_path.exists()

def test_ensure_database_exists_file_already_exists(tmp_path):
    """Test when database file already exists."""
    db_path = tmp_path / "test.db"
    db_path.touch()
    config = {"type": "sqlite", "path": str(db_path)}
    driver = UniversalDriver(config)
    
    result = driver.ensure_database_exists()
    assert result is True
    assert db_path.exists()
```

---

### Step 1.4: Implement Database Connection and Schema Initialization

**Goal**: Add logic to create CodeDatabase instance and initialize schema.

**Implementation**:
```python
def get_database(self) -> CodeDatabase:
    """
    Get CodeDatabase instance for operations.
    
    Creates instance if not exists, ensures database is initialized.
    
    Returns:
        CodeDatabase instance
    """
    if self._database is not None:
        return self._database
    
    # Ensure database exists
    if not self.ensure_database_exists():
        raise RuntimeError("Failed to ensure database exists")
    
    # Create driver config based on database type
    driver_config = self._create_driver_config()
    
    # Create CodeDatabase with auto_create_schema=True
    self._database = CodeDatabase(driver_config, auto_create_schema=True)
    
    # Initialize schema
    self.initialize_schema()
    
    self._initialized = True
    logger.info(f"Database initialized: {self.db_type}")
    
    return self._database

def _create_driver_config(self) -> Dict[str, Any]:
    """Create driver configuration based on database type."""
    if self.db_type == "sqlite":
        # For SQLite, always use proxy driver (commands never use direct driver)
        return {
            "type": "sqlite_proxy",
            "config": {
                "path": self.db_config["path"],
                "worker_config": self.db_config.get("worker_config", {}),
            },
        }
    else:
        # For other databases, use direct drivers (future)
        return {
            "type": self.db_type,
            "config": self.db_config,
        }

def initialize_schema(self) -> None:
    """
    Initialize database schema if not exists.
    
    This is called automatically by get_database(), but can be called
    explicitly if needed.
    """
    if self._database is None:
        raise RuntimeError("Database not initialized. Call get_database() first.")
    
    # Schema creation is handled by CodeDatabase with auto_create_schema=True
    # This method is here for explicit schema initialization if needed
    logger.debug("Schema initialization handled by CodeDatabase")
```

**Checklist**:
- [ ] `get_database()` method implemented
- [ ] `_create_driver_config()` method implemented
- [ ] SQLite uses sqlite_proxy driver
- [ ] Database initialization works
- [ ] Schema initialization works
- [ ] Error handling added

**Tests**:
```python
def test_get_database_creates_instance(tmp_path):
    """Test database instance creation."""
    db_path = tmp_path / "test.db"
    config = {"type": "sqlite", "path": str(db_path)}
    driver = UniversalDriver(config)
    
    db = driver.get_database()
    assert db is not None
    assert isinstance(db, CodeDatabase)
    assert driver._initialized is True

def test_get_database_uses_sqlite_proxy(tmp_path):
    """Test that SQLite uses proxy driver."""
    db_path = tmp_path / "test.db"
    config = {"type": "sqlite", "path": str(db_path)}
    driver = UniversalDriver(config)
    
    db = driver.get_database()
    # Verify driver is proxy (check driver type)
    assert db._driver_type == "sqlite_proxy"

def test_get_database_creates_schema(tmp_path):
    """Test schema creation."""
    db_path = tmp_path / "test.db"
    config = {"type": "sqlite", "path": str(db_path)}
    driver = UniversalDriver(config)
    
    db = driver.get_database()
    # Verify schema exists by querying projects table
    result = db._fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
    assert result is not None

def test_get_database_idempotent(tmp_path):
    """Test that get_database() returns same instance."""
    db_path = tmp_path / "test.db"
    config = {"type": "sqlite", "path": str(db_path)}
    driver = UniversalDriver(config)
    
    db1 = driver.get_database()
    db2 = driver.get_database()
    assert db1 is db2
```

---

### Step 1.5: Implement Close Method and Context Manager

**Goal**: Add cleanup logic and context manager support.

**Implementation**:
```python
def close(self) -> None:
    """Close database connection."""
    if self._database is not None:
        self._database.close()
        self._database = None
        self._initialized = False
        logger.debug("Database connection closed")

def __enter__(self):
    """Context manager entry."""
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    """Context manager exit."""
    self.close()
    return False
```

**Checklist**:
- [ ] `close()` method implemented
- [ ] Context manager support added
- [ ] Resources properly cleaned up
- [ ] Logging added

**Tests**:
```python
def test_close_closes_database(tmp_path):
    """Test database closing."""
    db_path = tmp_path / "test.db"
    config = {"type": "sqlite", "path": str(db_path)}
    driver = UniversalDriver(config)
    
    driver.get_database()
    driver.close()
    assert driver._database is None
    assert not driver._initialized

def test_context_manager(tmp_path):
    """Test context manager usage."""
    db_path = tmp_path / "test.db"
    config = {"type": "sqlite", "path": str(db_path)}
    
    with UniversalDriver(config) as driver:
        db = driver.get_database()
        assert db is not None
    
    # After context exit, database should be closed
    assert driver._database is None
```

---

## Phase 2: Refactor CodeDatabase

### Step 2.1: Add auto_create_schema Parameter

**Goal**: Modify CodeDatabase to accept `auto_create_schema` parameter and make schema creation conditional.

**Files to Modify**:
- `code_analysis/core/database/base.py`

**Implementation**:
```python
def __init__(self, driver_config: Dict[str, Any], auto_create_schema: bool = False) -> None:
    """
    Initialize database connection and optionally create schema.
    
    Args:
        driver_config: Driver configuration dict with 'type' and 'config' keys.
        auto_create_schema: If True, create schema on init (default: False).
                          Set to False when schema is managed externally.
    
    Raises:
        ValueError: If driver_config is missing or invalid.
    """
    # ... existing driver initialization code ...
    
    # Create schema only if requested
    if auto_create_schema:
        self._create_schema()
    else:
        logger.debug("Schema creation skipped (auto_create_schema=False)")
```

**Checklist**:
- [ ] `auto_create_schema` parameter added to `__init__`
- [ ] Schema creation is conditional
- [ ] Default value is `False` (backward compatible)
- [ ] Logging added for both paths
- [ ] Docstring updated

**Tests**:
```python
def test_code_database_with_auto_create_schema(tmp_path):
    """Test CodeDatabase with auto_create_schema=True."""
    driver_config = {
        "type": "sqlite_proxy",
        "config": {"path": str(tmp_path / "test.db")},
    }
    db = CodeDatabase(driver_config, auto_create_schema=True)
    
    # Verify schema exists
    result = db._fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
    assert result is not None

def test_code_database_without_auto_create_schema(tmp_path):
    """Test CodeDatabase with auto_create_schema=False."""
    driver_config = {
        "type": "sqlite_proxy",
        "config": {"path": str(tmp_path / "test.db")},
    }
    db = CodeDatabase(driver_config, auto_create_schema=False)
    
    # Schema should not exist
    result = db._fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
    assert result is None

def test_code_database_backward_compatible(tmp_path):
    """Test backward compatibility (default auto_create_schema=False)."""
    driver_config = {
        "type": "sqlite_proxy",
        "config": {"path": str(tmp_path / "test.db")},
    }
    db = CodeDatabase(driver_config)  # No auto_create_schema parameter
    
    # Should work without error
    assert db is not None
```

---

### Step 2.2: Update All CodeDatabase Instantiations

**Goal**: Find and update all places where CodeDatabase is created to use new signature.

**Files to Check**:
- `code_analysis/commands/base_mcp_command.py`
- `code_analysis/main.py`
- `code_analysis/core/database/__init__.py`
- All test files

**Checklist**:
- [ ] All CodeDatabase instantiations found
- [ ] Updated to use `auto_create_schema=False` where appropriate
- [ ] Tests updated
- [ ] No regressions in functionality

**Tests**:
```python
# Run existing tests to ensure no regressions
def test_all_existing_tests_pass():
    """Run full test suite to ensure backward compatibility."""
    # This should be run via pytest
    pass
```

---

## Phase 3: Refactor DBWorkerManager

### Step 3.1: Add Config Reading to DBWorkerManager

**Goal**: Add ability to read database configuration and determine database type.

**Files to Modify**:
- `code_analysis/core/db_worker_manager.py`

**Implementation**:
```python
def initialize_from_config(self, config: Dict[str, Any]) -> None:
    """
    Initialize DB workers from configuration.
    
    Args:
        config: Application configuration dict with 'code_analysis' section
    """
    code_analysis_config = config.get("code_analysis", {})
    if not code_analysis_config:
        logger.warning("No code_analysis config found, skipping DB worker initialization")
        return
    
    db_config = code_analysis_config.get("database", {})
    if not db_config:
        logger.warning("No database config found, skipping DB worker initialization")
        return
    
    db_type = self.get_db_type(db_config)
    logger.info(f"Database type detected: {db_type}")
    
    if db_type == "sqlite":
        db_path = db_config.get("path")
        if not db_path:
            logger.warning("SQLite database path not found in config")
            return
        
        worker_config = db_config.get("worker", {})
        worker_log_path = worker_config.get("log_path")
        
        # Ensure DB worker is running
        self.ensure_worker_running(db_path, db_type, worker_log_path)
    else:
        logger.info(f"DB worker not needed for {db_type} (direct connection)")

def get_db_type(self, db_config: Dict[str, Any]) -> str:
    """
    Determine database type from config.
    
    Args:
        db_config: Database configuration
        
    Returns:
        Database type string (sqlite, mysql, postgresql, etc.)
    """
    return db_config.get("type", "sqlite")

def ensure_worker_running(
    self, db_path: str, db_type: str, worker_log_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ensure DB worker is running for given database.
    
    Args:
        db_path: Path to database file
        db_type: Database type
        worker_log_path: Optional log path for worker
        
    Returns:
        Worker info dict
    """
    if db_type != "sqlite":
        raise ValueError(f"DB worker only needed for SQLite, got {db_type}")
    
    # Use existing get_or_start_worker logic
    return self.get_or_start_worker(db_path, worker_log_path)
```

**Checklist**:
- [ ] `initialize_from_config()` method implemented
- [ ] `get_db_type()` method implemented
- [ ] `ensure_worker_running()` method implemented
- [ ] SQLite detection works
- [ ] Config parsing works
- [ ] Error handling added

**Tests**:
```python
def test_initialize_from_config_sqlite(tmp_path):
    """Test initialization from config for SQLite."""
    db_path = tmp_path / "test.db"
    config = {
        "code_analysis": {
            "database": {
                "type": "sqlite",
                "path": str(db_path),
                "worker": {"log_path": str(tmp_path / "worker.log")},
            }
        }
    }
    
    manager = DBWorkerManager()
    manager.initialize_from_config(config)
    
    # Verify worker was started
    worker_info = manager.get_or_start_worker(str(db_path))
    assert worker_info is not None
    assert "socket_path" in worker_info

def test_get_db_type_sqlite():
    """Test SQLite type detection."""
    manager = DBWorkerManager()
    config = {"type": "sqlite", "path": "test.db"}
    assert manager.get_db_type(config) == "sqlite"

def test_get_db_type_default():
    """Test default type detection."""
    manager = DBWorkerManager()
    config = {"path": "test.db"}
    assert manager.get_db_type(config) == "sqlite"

def test_ensure_worker_running_sqlite(tmp_path):
    """Test worker startup for SQLite."""
    db_path = tmp_path / "test.db"
    manager = DBWorkerManager()
    
    worker_info = manager.ensure_worker_running(str(db_path), "sqlite")
    assert worker_info is not None
    assert "socket_path" in worker_info

def test_ensure_worker_running_non_sqlite():
    """Test that non-SQLite databases don't need workers."""
    manager = DBWorkerManager()
    
    with pytest.raises(ValueError, match="only needed for SQLite"):
        manager.ensure_worker_running("test", "mysql")
```

---

### Step 3.2: Integrate DBWorkerManager with WorkerManager

**Goal**: Register DB workers with WorkerManager for unified management.

**Implementation**:
```python
def ensure_worker_running(
    self, db_path: str, db_type: str, worker_log_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ensure DB worker is running for given database.
    
    Also registers worker with WorkerManager for unified management.
    """
    # ... existing worker startup logic ...
    
    # Register with WorkerManager
    from ..worker_manager import get_worker_manager
    
    worker_manager = get_worker_manager()
    worker_manager.register_worker(
        "database",
        {
            "pid": worker_info["pid"],
            "process": worker_info.get("process"),
            "name": f"db_worker_{Path(db_path).name}",
            "db_path": db_path,
            "db_type": db_type,
        },
    )
    
    logger.info(f"DB worker registered with WorkerManager: {db_path}")
    
    return worker_info
```

**Checklist**:
- [ ] DB workers registered with WorkerManager
- [ ] Worker info includes db_path and db_type
- [ ] Logging added
- [ ] Integration works correctly

**Tests**:
```python
def test_db_worker_registered_with_worker_manager(tmp_path):
    """Test that DB worker is registered with WorkerManager."""
    db_path = tmp_path / "test.db"
    manager = DBWorkerManager()
    
    worker_info = manager.ensure_worker_running(str(db_path), "sqlite")
    
    from code_analysis.core.worker_manager import get_worker_manager
    worker_manager = get_worker_manager()
    
    # Check registration
    workers = worker_manager.get_workers("database")
    assert len(workers) > 0
    assert any(w.get("db_path") == str(db_path) for w in workers)
```

---

### Step 3.3: Update Main.py to Use DBWorkerManager.initialize_from_config

**Goal**: Update server startup to initialize DB workers from config.

**Files to Modify**:
- `code_analysis/main.py`

**Implementation**:
```python
# In main() function, after config loading:

# Initialize DB workers from config
from code_analysis.core.db_worker_manager import get_db_worker_manager

db_worker_manager = get_db_worker_manager()
db_worker_manager.initialize_from_config(app_config)
```

**Checklist**:
- [ ] DBWorkerManager initialized from config in main()
- [ ] DB workers started automatically for SQLite
- [ ] Integration with existing startup flow
- [ ] Error handling added

**Tests**:
```python
# Integration test
def test_server_startup_initializes_db_worker(tmp_path, monkeypatch):
    """Test that server startup initializes DB worker."""
    db_path = tmp_path / "test.db"
    config = {
        "code_analysis": {
            "database": {
                "type": "sqlite",
                "path": str(db_path),
            }
        }
    }
    
    # Mock config loading
    # ... test implementation ...
```

---

## Phase 4: Unify Worker Startup

### Step 4.1: Create Worker Startup Helpers

**Goal**: Extract common worker startup logic to eliminate duplication.

**Files to Create**:
- `code_analysis/core/worker_startup_helpers.py`

**Implementation**: (See `docs/WORKER_INITIALIZATION_ANALYSIS.md` for details)

**Checklist**:
- [ ] `load_worker_config()` function created
- [ ] `resolve_worker_storage()` function created
- [ ] `is_worker_enabled()` function created
- [ ] `ensure_database_exists()` function created
- [ ] All functions tested

**Tests**:
```python
def test_load_worker_config_success():
    """Test successful config loading."""
    # Mock config
    config, server_config = load_worker_config()
    assert config is not None
    assert server_config is not None

def test_load_worker_config_missing():
    """Test config loading when config is missing."""
    # Mock missing config
    config, server_config = load_worker_config()
    assert config is None
    assert server_config is None
```

---

### Step 4.2: Refactor startup_vectorization_worker

**Goal**: Use worker startup helpers to eliminate duplication.

**Files to Modify**:
- `code_analysis/main.py`

**Implementation**:
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
        
        # ... rest of function using helpers ...
        
    except Exception as e:
        logger.error(f"❌ Failed to start vectorization worker: {e}", exc_info=True)
```

**Checklist**:
- [ ] Function refactored to use helpers
- [ ] Code duplication eliminated
- [ ] Functionality preserved
- [ ] Tests pass

**Tests**:
```python
def test_startup_vectorization_worker_uses_helpers():
    """Test that startup function uses helpers."""
    # Mock helpers and verify calls
    pass
```

---

### Step 4.3: Refactor startup_file_watcher_worker

**Goal**: Use worker_launcher and helpers to eliminate duplication.

**Files to Modify**:
- `code_analysis/main.py`

**Implementation**:
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
        else:
            logger.warning(f"⚠️  Failed to start file watcher worker: {result.message}")
        
    except Exception as e:
        logger.error(f"❌ Failed to start file watcher worker: {e}", exc_info=True)
```

**Checklist**:
- [ ] Function refactored to use worker_launcher
- [ ] Function refactored to use helpers
- [ ] Direct Process creation removed
- [ ] Code duplication eliminated
- [ ] Functionality preserved

**Tests**:
```python
def test_startup_file_watcher_worker_uses_launcher():
    """Test that file watcher uses worker_launcher."""
    # Mock worker_launcher and verify call
    pass
```

---

## Phase 5: Update Commands to Use UniversalDriver

### Step 5.1: Update BaseMCPCommand._open_database

**Goal**: Modify BaseMCPCommand to use UniversalDriver instead of direct CodeDatabase creation.

**Files to Modify**:
- `code_analysis/commands/base_mcp_command.py`

**Implementation**:
```python
def _open_database(
    self, root_dir: str, auto_analyze: bool = True
) -> CodeDatabase:
    """
    Open database connection using UniversalDriver.
    
    Args:
        root_dir: Root directory or project ID
        auto_analyze: If True, trigger analysis if database is empty
        
    Returns:
        CodeDatabase instance
    """
    from code_analysis.core.database.universal_driver import UniversalDriver
    from code_analysis.core.storage_paths import (
        load_raw_config,
        resolve_storage_paths,
        ensure_storage_dirs,
    )
    
    root_path = self._validate_root_dir(root_dir)
    
    # Resolve config and storage
    config_path = self._resolve_config_path()
    config_data = load_raw_config(config_path)
    storage = resolve_storage_paths(config_data=config_data, config_path=config_path)
    ensure_storage_dirs(storage)
    
    # Create database config
    db_config = {
        "type": "sqlite",
        "path": str(storage.db_path),
        "worker_config": {
            "command_timeout": 30.0,
            "poll_interval": 0.1,
        },
    }
    
    # Use UniversalDriver
    universal_driver = UniversalDriver(db_config)
    db = universal_driver.get_database()
    
    # Store driver for cleanup
    self._universal_driver = universal_driver
    
    # Auto-analysis logic (existing)
    if auto_analyze:
        # ... existing auto-analysis logic ...
    
    return db
```

**Checklist**:
- [ ] `_open_database()` updated to use UniversalDriver
- [ ] Database config created correctly
- [ ] UniversalDriver instance stored for cleanup
- [ ] Auto-analysis logic preserved
- [ ] Backward compatibility maintained

**Tests**:
```python
def test_base_mcp_command_uses_universal_driver(tmp_path):
    """Test that BaseMCPCommand uses UniversalDriver."""
    # Create test command instance
    # Verify UniversalDriver is used
    pass

def test_base_mcp_command_database_initialization(tmp_path):
    """Test database initialization through UniversalDriver."""
    # Verify database is created and initialized
    pass
```

---

### Step 5.2: Update Command Cleanup

**Goal**: Ensure UniversalDriver is properly closed when commands finish.

**Implementation**:
```python
# In BaseMCPCommand, add cleanup:
def __del__(self):
    """Cleanup UniversalDriver on command destruction."""
    if hasattr(self, "_universal_driver"):
        try:
            self._universal_driver.close()
        except Exception:
            pass
```

**Checklist**:
- [ ] Cleanup logic added
- [ ] UniversalDriver closed properly
- [ ] Error handling in cleanup

**Tests**:
```python
def test_command_cleanup_closes_driver():
    """Test that command cleanup closes UniversalDriver."""
    pass
```

---

## Phase 6: Testing and Validation

### Step 6.1: Unit Tests

**Goal**: Create comprehensive unit tests for all new components.

**Test Files to Create**:
- `tests/test_universal_driver.py`
- `tests/test_worker_startup_helpers.py`
- `tests/test_db_worker_manager_integration.py`

**Checklist**:
- [ ] UniversalDriver fully tested
- [ ] Worker startup helpers tested
- [ ] DBWorkerManager integration tested
- [ ] CodeDatabase refactoring tested
- [ ] All tests pass

**Test Coverage Goals**:
- UniversalDriver: >90%
- Worker helpers: >90%
- Integration tests: >80%

---

### Step 6.2: Integration Tests

**Goal**: Test full workflow from command to database.

**Test Scenarios**:
1. Command → UniversalDriver → Database → Query
2. Server startup → DB worker → Other workers
3. Database initialization → Schema creation → Operations
4. Worker startup → Registration → Operations

**Checklist**:
- [ ] Full command workflow tested
- [ ] Server startup workflow tested
- [ ] Database initialization workflow tested
- [ ] Worker startup workflow tested
- [ ] All integration tests pass

---

### Step 6.3: Performance Tests

**Goal**: Ensure no performance regression.

**Tests**:
- Database connection time
- Query execution time
- Worker startup time
- Memory usage

**Checklist**:
- [ ] Performance benchmarks created
- [ ] No significant performance regression
- [ ] Memory usage acceptable

---

### Step 6.4: Backward Compatibility Tests

**Goal**: Ensure existing functionality still works.

**Tests**:
- All existing commands work
- Existing configs work
- Existing databases work
- No breaking changes

**Checklist**:
- [ ] All existing tests pass
- [ ] Existing commands work
- [ ] Existing configs work
- [ ] No regressions

---

## Final Checklist

### Code Quality
- [ ] All code follows project style guidelines
- [ ] All functions have docstrings
- [ ] Type hints added where appropriate
- [ ] No code duplication
- [ ] Error handling comprehensive

### Documentation
- [ ] Architecture documented
- [ ] API documented
- [ ] Migration guide written
- [ ] Examples provided

### Testing
- [ ] Unit tests: >90% coverage for new code
- [ ] Integration tests: All workflows tested
- [ ] Performance tests: No regression
- [ ] Backward compatibility: All tests pass

### Deployment
- [ ] Code reviewed
- [ ] Tests pass in CI
- [ ] Documentation updated
- [ ] Migration plan ready

---

## Success Metrics

### Functional
- ✅ All workers start through WorkerManager
- ✅ Database access goes through UniversalDriver → CodeDatabase → SpecificDriver
- ✅ Database initialization handled by UniversalDriver
- ✅ DB worker started automatically for SQLite databases
- ✅ No code duplication in worker startup
- ✅ Commands work without changes (internal refactoring)

### Non-Functional
- ✅ Backward compatibility with existing configs
- ✅ Performance: No regression in database access speed
- ✅ Maintainability: Clear separation of concerns
- ✅ Testability: All components unit tested
- ✅ Documentation: Architecture documented

### Code Quality
- ✅ Zero code duplication in worker startup
- ✅ All workers use worker_launcher
- ✅ Consistent error handling
- ✅ Proper logging at all levels

---

## Timeline

**Estimated Duration**: 6 weeks

**Week 1**: Phase 1 (UniversalDriver)
**Week 2**: Phase 2 (CodeDatabase refactoring)
**Week 3**: Phase 3 (DBWorkerManager integration)
**Week 4**: Phase 4 (Worker startup unification)
**Week 5**: Phase 5 (Command updates)
**Week 6**: Phase 6 (Testing and validation)

---

## Notes

- Each phase should be completed and tested before moving to next
- Backward compatibility must be maintained throughout
- All tests must pass before proceeding to next step
- Code review required after each phase
