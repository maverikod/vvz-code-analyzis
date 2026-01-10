# Database Access Architecture Analysis

## Problem Statement

Commands are accessing the database through different mechanisms, violating the unified driver pattern. This causes:
1. Inconsistent database path resolution
2. Different database instances being accessed
3. Inconsistent results between commands

## Current Architecture

### Unified Pattern (CORRECT) - Used by Most Commands

**Pattern**: Commands inherit from `BaseMCPCommand` and use `_open_database()`

**Flow**:
```
Command.execute()
  → self._open_database(root_dir)
    → BaseMCPCommand._open_database(root_dir)
      → resolve_storage_paths(config_data, config_path)
      → storage.db_path (from config)
      → create_driver_config_for_worker(db_path)
      → CodeDatabase(driver_config)
      → Returns CodeDatabase instance
```

**Example Commands Using This Pattern**:
- `check_vectors` (CheckVectorsCommand)
- `get_ast` (GetASTMCPCommand)
- `list_project_files` (ListProjectFilesMCPCommand)
- Most other MCP commands

**Code Location**: `code_analysis/commands/base_mcp_command.py:124-301`

**Key Features**:
- Path resolution via config (`resolve_storage_paths`)
- Database integrity checks
- Automatic schema creation
- Optional auto-analysis
- Unified driver configuration

### Broken Pattern (INCORRECT) - Used by get_database_status

**Pattern**: Direct path construction and `DatabaseStatusCommand` class

**Flow**:
```
GetDatabaseStatusMCPCommand.execute()
  → root_path / "data" / "code_analysis.db" (DIRECT PATH)
  → DatabaseStatusCommand(db_path)
    → DatabaseStatusCommand.execute()
      → create_driver_config_for_worker(self.db_path)
      → CodeDatabase(driver_config)
```

**Code Locations**:
- `code_analysis/commands/worker_status_mcp_commands.py:409-416`
- `code_analysis/commands/worker_status.py:328-365`

**Problems**:
1. **Direct path construction**: `data_dir = root_path / "data"` bypasses config
2. **No integrity checks**: Doesn't use `_ensure_database_integrity()`
3. **Separate command class**: `DatabaseStatusCommand` is not an MCP command
4. **Different database path**: May access different database than other commands

## Database Access Objects and Blocks

### 1. BaseMCPCommand._open_database()

**Purpose**: Unified database access method for all MCP commands

**Responsibilities**:
- Resolve database path from config (not from `root_dir`)
- Check database integrity
- Create driver configuration
- Initialize `CodeDatabase` instance
- Optional auto-analysis

**Key Code**:
```python
@staticmethod
def _open_database(root_dir: str, auto_analyze: bool = True) -> CodeDatabase:
    root_path = normalize_root_dir(root_dir)
    
    # Resolve DB path from server config (NOT from root_dir!)
    config_path = BaseMCPCommand._resolve_config_path()
    config_data = load_raw_config(config_path)
    storage = resolve_storage_paths(config_data=config_data, config_path=config_path)
    db_path = storage.db_path  # From config, not root_dir/data/...
    
    # Integrity check
    integrity = BaseMCPCommand._ensure_database_integrity(db_path)
    
    # Create database
    driver_config = create_driver_config_for_worker(db_path)
    db = CodeDatabase(driver_config=driver_config)
    
    return db
```

### 2. CodeDatabase Class

**Purpose**: Unified database interface with pluggable drivers

**Location**: `code_analysis/core/database/base.py:70`

**Key Features**:
- Driver abstraction (SQLite, SQLite Proxy, etc.)
- Thread-safe operations
- Transaction support
- Dynamic method injection from modules

**Initialization**:
```python
def __init__(self, driver_config: Dict[str, Any]) -> None:
    driver_type = driver_config.get("type")
    driver_cfg = driver_config.get("config", {})
    self.driver = create_driver(driver_type, driver_cfg)
    self._create_schema()
```

### 3. Driver Configuration

**Purpose**: Create driver config from database path

**Location**: `code_analysis/core/database/base.py:20-53`

**Function**: `create_driver_config_for_worker(db_path: Path)`

**Returns**:
```python
{
    "type": "sqlite_proxy",  # or "sqlite"
    "config": {
        "db_path": str(db_path),
        # ... other driver-specific config
    }
}
```

### 4. resolve_storage_paths()

**Purpose**: Resolve database path from configuration

**Location**: `code_analysis/core/storage_paths.py:72-139`

**Logic**:
1. Read `code_analysis.storage.db_path` (new format)
2. Fallback to `code_analysis.db_path` (legacy format)
3. Default to `data/code_analysis.db` (relative to config dir)
4. Resolve relative paths against config directory

**Key Point**: Database path is resolved from **config directory**, NOT from `root_dir`!

## The Problem with get_database_status

### Current Implementation

```python
# worker_status_mcp_commands.py:409-416
async def execute(self, root_dir: str, **kwargs):
    root_path = self._validate_root_dir(root_dir)
    data_dir = root_path / "data"  # ❌ WRONG: Direct path construction
    db_path = data_dir / "code_analysis.db"  # ❌ WRONG: Ignores config
    
    command = DatabaseStatusCommand(db_path=str(db_path))
    result = await command.execute()
    return SuccessResult(data=result)
```

### What It Should Be

```python
async def execute(self, root_dir: str, **kwargs):
    root_path = self._validate_root_dir(root_dir)
    db = self._open_database(root_dir)  # ✅ CORRECT: Use unified method
    
    # Use db directly instead of DatabaseStatusCommand
    # ... query database ...
    
    db.close()
    return SuccessResult(data=result)
```

## Impact

1. **Different Database Paths**:
   - `get_database_status`: `root_dir/data/code_analysis.db`
   - `check_vectors`: `config_dir/data/code_analysis.db` (from config)
   - If `root_dir != config_dir`, they access different databases!

2. **Missing Integrity Checks**:
   - `get_database_status` doesn't check database integrity
   - Other commands do check via `_ensure_database_integrity()`

3. **Inconsistent Results**:
   - Commands may see different data
   - Different transaction states
   - Different database instances

## Solution

### Fix get_database_status

1. **Remove `DatabaseStatusCommand` class** (or make it internal)
2. **Use `_open_database()` in `GetDatabaseStatusMCPCommand`**
3. **Query database directly** using `CodeDatabase` instance
4. **Ensure consistent path resolution** via config

### Standardize All Commands

All commands should:
1. Inherit from `BaseMCPCommand`
2. Use `self._open_database(root_dir)` to get database
3. Never construct database paths directly
4. Always close database connection when done

## Verification

To verify all commands use unified access:

```bash
# Find commands that construct db_path directly
grep -r "db_path.*=.*data.*code_analysis" code_analysis/commands/

# Find commands that use _open_database (correct)
grep -r "_open_database" code_analysis/commands/

# Find DatabaseStatusCommand usage (should be removed)
grep -r "DatabaseStatusCommand" code_analysis/commands/
```

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
