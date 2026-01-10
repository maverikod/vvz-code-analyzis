# Database Schema Sync - Proposed Solutions

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-10

## Решения для выявленных проблем

### Проблема 1: `_create_schema()` - декларативность vs выполнение SQL

**Вариант A: Двойное определение (РЕКОМЕНДУЕТСЯ)**

Создать структурированное определение схемы отдельно от SQL, но использовать SQL как источник истины для обратной совместимости.

```python
# В base.py

# Schema version
SCHEMA_VERSION = "1.0.0"

# Migration methods registry
MIGRATION_METHODS: Dict[str, Callable[[BaseDatabaseDriver], None]] = {
    # Format: "version": lambda driver: driver._migration_method_name()
}

def _get_schema_definition(self) -> Dict[str, Any]:
    """
    Get structured schema definition for synchronization.
    
    This method builds schema definition from structured data,
    not by parsing SQL (more reliable and maintainable).
    """
    return {
        "version": SCHEMA_VERSION,
        "tables": {
            "projects": {
                "columns": [
                    {"name": "id", "type": "TEXT", "not_null": True, "primary_key": True},
                    {"name": "root_path", "type": "TEXT", "not_null": True, "unique": True},
                    {"name": "name", "type": "TEXT", "not_null": False},
                    {"name": "comment", "type": "TEXT", "not_null": False},
                    {"name": "created_at", "type": "REAL", "not_null": False, "default": "julianday('now')"},
                    {"name": "updated_at", "type": "REAL", "not_null": False, "default": "julianday('now')"},
                ],
                "foreign_keys": [],
                "unique_constraints": [{"columns": ["root_path"]}],
                "check_constraints": [],
            },
            "datasets": {
                "columns": [
                    {"name": "id", "type": "TEXT", "not_null": True, "primary_key": True},
                    {"name": "project_id", "type": "TEXT", "not_null": True},
                    {"name": "root_path", "type": "TEXT", "not_null": True},
                    {"name": "name", "type": "TEXT", "not_null": False},
                    {"name": "created_at", "type": "REAL", "not_null": False, "default": "julianday('now')"},
                    {"name": "updated_at", "type": "REAL", "not_null": False, "default": "julianday('now')"},
                ],
                "foreign_keys": [
                    {
                        "columns": ["project_id"],
                        "references_table": "projects",
                        "references_columns": ["id"],
                        "on_delete": "CASCADE"
                    }
                ],
                "unique_constraints": [{"columns": ["project_id", "root_path"]}],
                "check_constraints": [],
            },
            "files": {
                "columns": [
                    {"name": "id", "type": "INTEGER", "not_null": True, "primary_key": True, "autoincrement": True},
                    {"name": "project_id", "type": "TEXT", "not_null": True},
                    {"name": "dataset_id", "type": "TEXT", "not_null": True},
                    {"name": "path", "type": "TEXT", "not_null": True},
                    {"name": "lines", "type": "INTEGER", "not_null": False},
                    {"name": "last_modified", "type": "REAL", "not_null": False},
                    {"name": "has_docstring", "type": "BOOLEAN", "not_null": False},
                    {"name": "deleted", "type": "BOOLEAN", "not_null": False, "default": "0"},
                    {"name": "original_path", "type": "TEXT", "not_null": False},
                    {"name": "version_dir", "type": "TEXT", "not_null": False},
                    {"name": "created_at", "type": "REAL", "not_null": False, "default": "julianday('now')"},
                    {"name": "updated_at", "type": "REAL", "not_null": False, "default": "julianday('now')"},
                ],
                "foreign_keys": [
                    {
                        "columns": ["project_id"],
                        "references_table": "projects",
                        "references_columns": ["id"],
                        "on_delete": "CASCADE"
                    },
                    {
                        "columns": ["dataset_id"],
                        "references_table": "datasets",
                        "references_columns": ["id"],
                        "on_delete": "CASCADE"
                    }
                ],
                "unique_constraints": [{"columns": ["project_id", "dataset_id", "path"]}],
                "check_constraints": [],
            },
            # ... остальные таблицы аналогично
            "db_settings": {
                "columns": [
                    {"name": "key", "type": "TEXT", "not_null": True, "primary_key": True},
                    {"name": "value", "type": "TEXT", "not_null": True},
                    {"name": "updated_at", "type": "REAL", "not_null": False, "default": "julianday('now')"},
                ],
                "foreign_keys": [],
                "unique_constraints": [],
                "check_constraints": [],
            },
        },
        "indexes": [
            {
                "name": "idx_files_deleted",
                "table": "files",
                "columns": ["deleted"],
                "unique": False,
                "where_clause": "deleted = 1"
            },
            # ... остальные индексы
        ],
        "virtual_tables": [
            {
                "name": "code_content_fts",
                "type": "fts5",
                "columns": ["entity_type", "entity_name", "content", "docstring"],
                "options": {
                    "content_rowid": "rowid",
                    "content": "code_content"
                }
            }
        ],
        "migration_methods": MIGRATION_METHODS
    }

def _create_schema_sql(self) -> None:
    """
    Create database schema using SQL (legacy method, kept for reference).
    
    This method is NOT called automatically - schema is created via sync_schema().
    Kept for documentation and as fallback if needed.
    """
    # ... existing SQL CREATE TABLE statements ...
    # This method can be used for initial schema creation in migration scripts
    pass
```

**Преимущества**:
- Четкое разделение: структурированное определение для сравнения, SQL для выполнения
- Легко поддерживать и расширять
- Не нужно парсить SQL

**Недостатки**:
- Дублирование (но это оправдано для надежности)

---

### Проблема 2: Сигнатуры `sync_schema()`

**РЕКОМЕНДУЕМОЕ РЕШЕНИЕ**: Единая сигнатура с явными параметрами

```python
# В CodeDatabase (base.py)
def sync_schema(self) -> Dict[str, Any]:
    """
    Synchronize database schema via driver.
    
    Returns:
        Dict with sync results from driver.
    """
    schema_definition = self._get_schema_definition()
    
    # Get backup_dir from storage paths (passed via driver config)
    # Driver config should include backup_dir from StoragePaths
    backup_dir = self.driver_config.get("config", {}).get("backup_dir")
    if not backup_dir:
        # Fallback: infer from db_path
        db_path = self.driver_config.get("config", {}).get("path")
        if db_path:
            db_path_obj = Path(db_path)
            if db_path_obj.parent.name == "data":
                backup_dir = str(db_path_obj.parent.parent / "backups")
            else:
                backup_dir = str(db_path_obj.parent / "backups")
        else:
            raise RuntimeError("Cannot determine backup_dir for schema sync")
    
    return self.driver.sync_schema(schema_definition, Path(backup_dir))

# В SQLiteDriverProxy (sqlite_proxy.py)
def sync_schema(
    self, 
    schema_definition: Dict[str, Any], 
    backup_dir: Path
) -> Dict[str, Any]:
    """
    Synchronize database schema via worker.
    
    Args:
        schema_definition: Schema definition from CodeDatabase
        backup_dir: Directory for database backups
    
    Returns:
        Dict with sync results from worker.
    """
    if not self._worker_initialized or not self._socket_path:
        raise RuntimeError("Worker not initialized")
    
    request = {
        "command": "sync_schema",
        "params": {
            "schema_definition": schema_definition,
            "backup_dir": str(backup_dir),
        },
    }
    
    response = self._send_request(request)
    if not response.get("success"):
        raise DatabaseOperationError(
            f"Schema sync failed: {response.get('error')}",
            operation="sync_schema"
        )
    
    return response.get("result", {})

# В SQLiteDriver (sqlite.py)
def sync_schema(
    self, 
    schema_definition: Dict[str, Any], 
    backup_dir: Path
) -> Dict[str, Any]:
    """
    Synchronize database schema.
    
    Args:
        schema_definition: Schema definition from CodeDatabase
        backup_dir: Directory for database backups
    
    Returns:
        Dict with sync results.
    """
    # ... implementation from Phase 4 ...
```

**Преимущества**:
- Явные параметры, легко тестировать
- Нет зависимости от CodeDatabase в driver
- Единообразная сигнатура во всех компонентах

---

### Проблема 3: Управление версией схемы

**РЕКОМЕНДУЕМОЕ РЕШЕНИЕ**: Версия управляется в Driver, CodeDatabase имеет обертку

```python
# В SQLiteDriver (sqlite.py)
def _get_schema_version(self) -> Optional[str]:
    """Get current schema version from database."""
    try:
        # Check if db_settings table exists
        result = self.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='db_settings'"
        )
        if not result:
            return None  # Table doesn't exist yet
        
        result = self.fetchone(
            "SELECT value FROM db_settings WHERE key = ?",
            ("schema_version",)
        )
        return result["value"] if result else None
    except Exception:
        return None

def _set_schema_version(self, version: str) -> None:
    """Set schema version in database."""
    # Ensure db_settings table exists
    self.execute(
        """
        CREATE TABLE IF NOT EXISTS db_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL DEFAULT (julianday('now'))
        )
        """
    )
    
    self.execute(
        """
        INSERT OR REPLACE INTO db_settings (key, value, updated_at)
        VALUES (?, ?, julianday('now'))
        """,
        ("schema_version", version)
    )
    self.commit()

# В CodeDatabase (base.py) - обертка для удобства
def get_schema_version(self) -> Optional[str]:
    """Get current schema version (delegates to driver)."""
    return self.driver.get_schema_version()

def set_schema_version(self, version: str) -> None:
    """Set schema version (delegates to driver)."""
    self.driver.set_schema_version(version)
```

**Преимущества**:
- Логика в Driver (имеет прямой доступ к БД)
- CodeDatabase может иметь обертки для удобства
- Четкое разделение ответственности

---

### Проблема 4: BackupManager и backup_dir

**РЕКОМЕНДУЕМОЕ РЕШЕНИЕ**: Отдельный метод для БД бэкапов, не смешивать с old_code

```python
# В backup_manager.py
class BackupManager:
    """Manages backup copies of files in old_code directory."""
    
    def __init__(self, root_dir: Path) -> None:
        """
        Initialize backup manager.
        
        Args:
            root_dir: Project root directory
        """
        self.root_dir = Path(root_dir).resolve()
        self.backup_dir = self.root_dir / "old_code"  # For code backups
        self.index_file = self.backup_dir / "index.txt"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def create_database_backup(
        self,
        db_path: Path,
        backup_dir: Path,  # Explicit backup directory (from StoragePaths)
        comment: str = "Schema synchronization backup",
    ) -> Optional[str]:
        """
        Create backup of database file and sidecar files.
        
        This method is separate from code backups (old_code) because:
        - Database backups are larger and may need different retention
        - Database backups are created automatically during schema sync
        - Code backups are manual/command-based
        
        Args:
            db_path: Path to database file
            backup_dir: Directory where to store backups (from StoragePaths.backup_dir)
            comment: Optional comment for backup
        
        Returns:
            UUID of created backup, or None if failed or DB is empty
        """
        try:
            db_path = Path(db_path).resolve()
            if not db_path.exists():
                _get_logger().warning(f"Database file not found: {db_path}")
                return None
            
            # Check if database is empty
            if self._is_database_empty(db_path):
                _get_logger().info("Database is empty, skipping backup")
                return None
            
            backup_dir = Path(backup_dir).resolve()
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            backup_uuid = str(uuid.uuid4())
            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            
            # Backup main database file
            backup_filename = f"database-{db_path.stem}-{timestamp}-{backup_uuid}.db"
            backup_path = backup_dir / backup_filename
            shutil.copy2(db_path, backup_path)
            
            # Backup sidecar files if they exist
            sidecar_extensions = [".wal", ".shm", ".journal"]
            sidecar_files = []
            for ext in sidecar_extensions:
                sidecar_path = db_path.with_suffix(db_path.suffix + ext)
                if sidecar_path.exists():
                    sidecar_backup = backup_dir / f"{backup_filename}{ext}"
                    shutil.copy2(sidecar_path, sidecar_backup)
                    sidecar_files.append(str(sidecar_backup.name))
            
            # Optionally: create index entry for database backup
            # (separate from code backup index, or use same format)
            _get_logger().info(
                f"Database backup created: {backup_path} (UUID: {backup_uuid})"
            )
            return backup_uuid
            
        except Exception as e:
            _get_logger().error(f"Failed to create database backup: {e}", exc_info=True)
            return None
    
    def _is_database_empty(self, db_path: Path) -> bool:
        """Check if database is empty (no tables or no data)."""
        # ... implementation from plan ...
```

**Преимущества**:
- Разделение: code backups (old_code) и database backups (backups)
- Гибкость: разные директории, разные политики retention
- Явный параметр backup_dir (из StoragePaths)

---

### Проблема 5: MIGRATION_METHODS - где хранить

**РЕКОМЕНДУЕМОЕ РЕШЕНИЕ**: Registry в base.py, методы принимают driver

```python
# В base.py (CodeDatabase)
# Migration methods registry: version -> migration function
# Each migration function receives driver instance and performs version-specific migrations
# Migration functions are called in order when upgrading from old version to new version
MIGRATION_METHODS: Dict[str, Callable[[BaseDatabaseDriver], None]] = {
    # Example:
    # "1.0.0": lambda driver: driver._migrate_to_uuid_projects(),
    # "1.1.0": lambda driver: driver._migrate_add_datasets_table(),
}

# В SQLiteDriver (sqlite.py) - методы миграции
def _migrate_to_uuid_projects(self) -> None:
    """Migration to UUID-based project IDs (example)."""
    # Implementation here
    pass

# В sync_schema() (sqlite.py)
from ..database.base import MIGRATION_METHODS

# Get migration versions between current and target version
migration_versions = sorted([
    v for v in MIGRATION_METHODS.keys() 
    if _version_compare(v, current_version) > 0 and _version_compare(v, code_version) <= 0
], key=lambda v: tuple(int(x) for x in v.split(".")))

for migration_version in migration_versions:
    migration_func = MIGRATION_METHODS[migration_version]
    logger.info(f"Running migration for version {migration_version}")
    migration_func(self)  # Pass driver instance
```

**Преимущества**:
- Registry в одном месте (base.py)
- Методы имеют доступ к driver для выполнения SQL
- Легко добавлять новые миграции

---

### Проблема 6: FTS5 таблицы - сохранение данных

**РЕКОМЕНДУЕМОЕ РЕШЕНИЕ**: Использовать content table для восстановления

```python
# В schema_sync.py (SchemaComparator)
def _recreate_virtual_table(
    self, 
    table_name: str, 
    virtual_table_def: Dict[str, Any]
) -> List[str]:
    """
    Generate SQL to recreate virtual table (FTS5) with data preservation.
    
    For FTS5 with external content table, data is stored in content table,
    so we only need to recreate FTS5 table - data will be re-indexed automatically.
    """
    statements = []
    
    # Check if FTS5 uses external content table
    content_table = virtual_table_def.get("options", {}).get("content")
    
    if content_table:
        # FTS5 with external content - data is in content table
        # Just drop and recreate FTS5, data will be re-indexed from content table
        statements.append(f"DROP TABLE IF EXISTS {table_name}")
        
        # Create new virtual table
        columns = ", ".join(virtual_table_def["columns"])
        options = virtual_table_def.get("options", {})
        options_str = ", ".join([f"{k}='{v}'" for k, v in options.items()])
        if options_str:
            create_sql = (
                f"CREATE VIRTUAL TABLE {table_name} "
                f"USING {virtual_table_def['type']}({columns}, {options_str})"
            )
        else:
            create_sql = (
                f"CREATE VIRTUAL TABLE {table_name} "
                f"USING {virtual_table_def['type']}({columns})"
            )
        statements.append(create_sql)
        
        # Rebuild FTS5 index from content table
        # FTS5 will automatically re-index from content table
        statements.append(
            f"INSERT INTO {table_name}({table_name}) VALUES('rebuild')"
        )
    else:
        # FTS5 without external content - need to backup data
        temp_table = f"temp_{table_name}"
        
        # Backup data (if any exists)
        statements.append(
            f"CREATE TEMP TABLE {temp_table} AS SELECT * FROM {table_name}"
        )
        
        # Drop virtual table
        statements.append(f"DROP TABLE IF EXISTS {table_name}")
        
        # Create new virtual table
        columns = ", ".join(virtual_table_def["columns"])
        create_sql = (
            f"CREATE VIRTUAL TABLE {table_name} "
            f"USING {virtual_table_def['type']}({columns})"
        )
        statements.append(create_sql)
        
        # Restore data (if any)
        statements.append(f"INSERT INTO {table_name} SELECT * FROM {temp_table}")
        
        # Drop temp table
        statements.append(f"DROP TABLE {temp_table}")
    
    return statements
```

**Преимущества**:
- Использует механизм FTS5 с external content
- Автоматическое переиндексирование из content table
- Безопасно для `code_content_fts` (использует `content='code_content'`)

---

### Проблема 7: Передача backup_dir через config

**РЕКОМЕНДУЕМОЕ РЕШЕНИЕ**: Добавить backup_dir в driver config при создании CodeDatabase

```python
# В месте создания CodeDatabase (например, в командах или main.py)
from code_analysis.core.storage_paths import resolve_storage_paths, ensure_storage_dirs

# Resolve storage paths
storage = resolve_storage_paths(config_data=config, config_path=config_path)
ensure_storage_dirs(storage)

# Create driver config with backup_dir
driver_config = {
    "type": "sqlite_proxy",
    "config": {
        "path": str(storage.db_path),
        "backup_dir": str(storage.backup_dir),  # NEW: Add backup_dir
        "worker_config": {
            # ... worker config ...
        }
    }
}

# Create CodeDatabase
database = CodeDatabase(driver_config)
```

**Преимущества**:
- Явная передача через config
- Нет необходимости выводить из db_path
- Единый источник истины (StoragePaths)

---

## Итоговая архитектура

### Flow синхронизации схемы:

```
1. CodeDatabase.__init__(driver_config)
   ↓
2. Create driver (SQLiteDriverProxy)
   ↓
3. SQLiteDriverProxy.connect(config)
   - Requests worker via DBWorkerManager.get_or_start_worker()
   - Worker creates empty DB if missing
   ↓
4. CodeDatabase.sync_schema()
   - Gets schema_definition from _get_schema_definition()
   - Gets backup_dir from driver_config["config"]["backup_dir"]
   - Calls driver.sync_schema(schema_definition, backup_dir)
   ↓
5. SQLiteDriverProxy.sync_schema(schema_definition, backup_dir)
   - Sends command to worker via socket
   ↓
6. Worker: _handle_client_connection() receives "sync_schema" command
   - Creates SQLiteDriver instance
   - Calls driver.sync_schema(schema_definition, backup_dir)
   ↓
7. SQLiteDriver.sync_schema(schema_definition, backup_dir)
   - Creates SchemaComparator
   - Compares schemas
   - Validates data compatibility
   - Creates backup (if needed)
   - Runs migration methods (if needed)
   - Applies schema changes
   - Updates schema version
```

### Ключевые решения:

1. ✅ **Схема**: Структурированное определение в `_get_schema_definition()`, SQL отдельно
2. ✅ **Сигнатуры**: Единая `sync_schema(schema_definition, backup_dir)` везде
3. ✅ **Версия**: Управляется в Driver, CodeDatabase имеет обертки
4. ✅ **Backup**: Отдельный метод для БД, backup_dir из StoragePaths
5. ✅ **Миграции**: Registry в base.py, методы принимают driver
6. ✅ **FTS5**: Использует external content для автоматического переиндексирования
7. ✅ **Config**: backup_dir передается через driver_config

## Следующие шаги

1. Обновить план с этими решениями
2. Начать реализацию Phase 1 с новой структурой
3. Тестировать каждую фазу по отдельности
