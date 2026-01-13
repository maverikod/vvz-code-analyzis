# Database Driver Development Standard

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-13

## Overview

This document defines the standard for developing database drivers (MySQL, PostgreSQL, etc.) for the code-analysis project. All drivers must follow this standard to ensure consistency, maintainability, and proper integration with the RPC-based architecture.

**⚠️ CRITICAL ARCHITECTURE PRINCIPLE:**

**Driver = RPC Server with Unified Interface**

- The driver **IS** an RPC server with a unified set of RPC methods
- All RPC methods work **ONLY with tables** (table_name, data, where clauses)
- Driver **does NOT know** about objects (Project, File, etc.)
- Client library performs **object ↔ table conversion**

## Architecture Context

### Driver Process Architecture

```
Main Process / Workers
  ↓
Client Library (object-oriented API)
  ├─ Object → Table conversion
  └─ RPC Client
      ↓
RPC Communication (Unix socket / TCP)
      ↓
Database Driver Process (separate process)
  ├─ RPC Server (unified interface)
  ├─ Request Queue (manages request queue)
  └─ Driver Implementation (SQLite, PostgreSQL, MySQL, etc.)
      ↓
Database (SQLite file, PostgreSQL server, MySQL server, etc.)
```

### Key Principles

1. **Driver = RPC Server**: Driver is an RPC server with unified interface
2. **Unified Interface**: All drivers (SQLite, PostgreSQL, MySQL) expose the same RPC methods
3. **Table-level operations**: All RPC methods work ONLY with tables (table_name, data dict, where dict)
4. **No object models**: Driver doesn't know about Project, File, etc. - only tables, columns, cells
5. **Client transformation**: Client library converts objects → tables (outgoing) and tables → objects (incoming)
6. **Request queue**: Queue is managed inside driver process
7. **Separate process**: Driver runs in separate process managed by WorkerManager

## Unified RPC Interface

### RPC Server Interface

**⚠️ CRITICAL: All drivers must expose the SAME unified RPC interface**

The driver is an RPC server that exposes a unified set of methods. All drivers (SQLite, PostgreSQL, MySQL, etc.) must implement the same RPC methods with identical signatures.

### RPC Methods (Unified Interface)

All drivers must implement these RPC methods:

```python
# Table operations
rpc.create_table(schema: dict) -> bool
rpc.drop_table(table_name: str) -> bool
rpc.alter_table(table_name: str, changes: dict) -> bool

# Data operations (ALL work with tables only)
rpc.insert(table_name: str, data: dict) -> int  # Returns row ID
rpc.update(table_name: str, where: dict, data: dict) -> int  # Returns affected rows
rpc.delete(table_name: str, where: dict) -> int  # Returns affected rows
rpc.select(
    table_name: str, 
    where: Optional[dict] = None, 
    columns: Optional[list] = None, 
    limit: Optional[int] = None, 
    offset: Optional[int] = None,
    order_by: Optional[list] = None
) -> list[dict]  # Returns list of row dicts

# Generic SQL execution
rpc.execute(sql: str, params: Optional[tuple] = None) -> dict

# Transaction operations
rpc.begin_transaction() -> str  # Returns transaction ID
rpc.commit_transaction(transaction_id: str) -> bool
rpc.rollback_transaction(transaction_id: str) -> bool

# Schema operations
rpc.get_table_info(table_name: str) -> list[dict]
rpc.get_schema_version() -> str
rpc.sync_schema(schema_definition: dict, backup_dir: Optional[str] = None) -> dict
```

**⚠️ IMPORTANT:**
- All methods work with **tables only** (table_name, data dict, where dict)
- Driver **does NOT** receive objects (Project, File, etc.)
- Driver **does NOT** know about object models
- Client library converts objects → tables before calling RPC methods

### RPC Method Parameters (Table-Level Only)

All RPC methods work with table-level parameters:

```python
# ✅ CORRECT: Table-level parameters
rpc.insert(table_name="projects", data={"id": "123", "name": "My Project"})
rpc.select(table_name="files", where={"project_id": "123"})
rpc.update(table_name="projects", where={"id": "123"}, data={"name": "New Name"})

# ❌ WRONG: Object-level parameters (driver does NOT accept these)
rpc.create_project(project=Project(...))  # Driver doesn't know about Project
rpc.get_file(file=File(...))  # Driver doesn't know about File
```

### BaseDriver Implementation Interface

While the RPC interface is unified, each driver must implement the `BaseDatabaseDriver` interface internally:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

class BaseDatabaseDriver(ABC):
    """
    Base class for database driver implementations.
    
    This is the INTERNAL implementation interface. The RPC server
    calls these methods to perform actual database operations.
    
    All drivers must implement this interface, but the RPC interface
    exposed to clients is unified and identical for all drivers.
    """
    
    @property
    @abstractmethod
    def driver_type(self) -> str:
        """Return driver type identifier (e.g., 'postgres', 'mysql')."""
        raise NotImplementedError
    
    @property
    @abstractmethod
    def is_thread_safe(self) -> bool:
        """
        Whether the driver is thread-safe.
        
        Returns:
            True if driver is thread-safe, False otherwise
        """
        raise NotImplementedError
    
    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> None:
        """
        Establish database connection.
        
        Args:
            config: Driver-specific configuration dictionary
            
        Raises:
            DriverConnectionError: If connection fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def disconnect(self) -> None:
        """
        Close database connection.
        
        Raises:
            DriverError: If disconnection fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def create_table(self, schema: Dict[str, Any]) -> bool:
        """
        Create table from schema definition.
        
        Args:
            schema: Table schema definition with keys:
                - name: Table name
                - columns: List of column definitions
                - constraints: List of constraint definitions
                - indexes: List of index definitions
                
        Returns:
            True if table created successfully, False otherwise
            
        Raises:
            DriverError: If table creation fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def drop_table(self, table_name: str) -> bool:
        """
        Drop table.
        
        Args:
            table_name: Name of table to drop
            
        Returns:
            True if table dropped successfully, False otherwise
            
        Raises:
            DriverError: If table drop fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def insert(self, table_name: str, data: Dict[str, Any]) -> int:
        """
        Insert row into table.
        
        Args:
            table_name: Name of table
            data: Dictionary with column names as keys and values
            
        Returns:
            Number of rows inserted (should be 1)
            
        Raises:
            DriverError: If insert fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def update(
        self, 
        table_name: str, 
        where: Dict[str, Any], 
        data: Dict[str, Any]
    ) -> int:
        """
        Update rows in table.
        
        Args:
            table_name: Name of table
            where: Dictionary with column names and values for WHERE clause
            data: Dictionary with column names and new values
            
        Returns:
            Number of rows updated
            
        Raises:
            DriverError: If update fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def delete(self, table_name: str, where: Dict[str, Any]) -> int:
        """
        Delete rows from table.
        
        Args:
            table_name: Name of table
            where: Dictionary with column names and values for WHERE clause
            
        Returns:
            Number of rows deleted
            
        Raises:
            DriverError: If delete fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[Tuple[str, str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Select rows from table.
        
        Args:
            table_name: Name of table
            where: Optional dictionary with column names and values for WHERE clause
            columns: Optional list of column names to select (None = all columns)
            limit: Optional maximum number of rows to return
            offset: Optional number of rows to skip
            order_by: Optional list of (column_name, direction) tuples
                      direction: 'ASC' or 'DESC'
        
        Returns:
            List of dictionaries, each representing a row with column names as keys
            
        Raises:
            DriverError: If select fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> Dict[str, Any]:
        """
        Execute raw SQL statement.
        
        Args:
            sql: SQL statement
            params: Optional parameters for parameterized query
            
        Returns:
            Dictionary with execution results:
                - affected_rows: Number of affected rows
                - last_insert_id: Last insert ID (if applicable)
                - data: Query results (if SELECT)
                
        Raises:
            DriverError: If execution fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def begin_transaction(self) -> str:
        """
        Begin transaction.
        
        Returns:
            Transaction ID (string identifier)
            
        Raises:
            DriverError: If transaction start fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def commit_transaction(self, transaction_id: str) -> bool:
        """
        Commit transaction.
        
        Args:
            transaction_id: Transaction ID returned by begin_transaction()
            
        Returns:
            True if commit successful, False otherwise
            
        Raises:
            DriverError: If commit fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def rollback_transaction(self, transaction_id: str) -> bool:
        """
        Rollback transaction.
        
        Args:
            transaction_id: Transaction ID returned by begin_transaction()
            
        Returns:
            True if rollback successful, False otherwise
            
        Raises:
            DriverError: If rollback fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Get table schema information.
        
        Args:
            table_name: Name of table
            
        Returns:
            List of dictionaries with column information:
                - name: Column name
                - type: Column type
                - nullable: Whether column is nullable
                - default: Default value (if any)
                - primary_key: Whether column is primary key
                
        Raises:
            DriverError: If query fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def sync_schema(
        self, 
        schema_definition: Dict[str, Any], 
        backup_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synchronize database schema with schema definition.
        
        Args:
            schema_definition: Complete schema definition with all tables
            backup_dir: Optional directory for backups before schema changes
            
        Returns:
            Dictionary with sync results:
                - created_tables: List of created table names
                - modified_tables: List of modified table names
                - errors: List of error messages (if any)
                
        Raises:
            DriverError: If schema sync fails critically
        """
        raise NotImplementedError
```

## Driver Package Structure

### Required Structure

```
code_analysis/core/database_driver_pkg/
├── __init__.py
├── runner.py                 # Driver process entry point
├── rpc_server.py             # RPC server with unified interface
├── request_queue.py          # Request queue management
├── request.py                # Base Request classes with abstract methods
├── result.py                 # Base Result classes with abstract methods
├── exceptions.py             # Driver exceptions
└── drivers/
    ├── __init__.py           # Driver registry and factory
    ├── base.py               # BaseDatabaseDriver interface (internal)
    ├── sqlite.py             # SQLite driver implementation (implements abstract methods)
    ├── postgres.py           # PostgreSQL driver implementation (extends base classes)
    └── mysql.py              # MySQL driver implementation (extends base classes)
```

### Base Request and Result Classes

**⚠️ CRITICAL: All drivers must use base Request and Result classes**

The RPC infrastructure provides base classes that must be extended by driver implementations:

1. **BaseRequest** - Abstract base class for all requests
   - Abstract methods: `validate()`, `to_dict()`, `from_dict()`
   - Concrete classes: `InsertRequest`, `SelectRequest`, `UpdateRequest`, `DeleteRequest`, `TransactionRequest`
   - SQLite driver must implement all abstract methods

2. **BaseResult** - Abstract base class for all results
   - Abstract methods: `to_dict()`, `from_dict()`, `is_success()`, `is_error()`
   - Concrete classes: `SuccessResult`, `ErrorResult`, `DataResult`
   - SQLite driver must implement all abstract methods

**See**: [Step 2: RPC Infrastructure](./STEP_02_RPC_INFRASTRUCTURE.md) for detailed requirements

### RPC Server Structure

The RPC server (`rpc_server.py`) provides the unified interface and calls driver methods:

```python
from .request import InsertRequest, SelectRequest, UpdateRequest, DeleteRequest
from .result import SuccessResult, ErrorResult, DataResult

class DatabaseDriverRPCServer:
    """RPC server with unified interface for all drivers."""
    
    def __init__(self, driver: BaseDatabaseDriver):
        """Initialize RPC server with driver implementation."""
        self.driver = driver
    
    def handle_request(self, request: BaseRequest) -> BaseResult:
        """
        Handle RPC request using base request/result classes.
        
        Args:
            request: Request instance (InsertRequest, SelectRequest, etc.)
            
        Returns:
            Result instance (SuccessResult, ErrorResult, DataResult)
        """
        try:
            # Validate request
            request.validate()
            
            # Route to appropriate handler
            if isinstance(request, InsertRequest):
                return self._handle_insert(request)
            elif isinstance(request, SelectRequest):
                return self._handle_select(request)
            # ... other request types ...
        except Exception as e:
            return ErrorResult(error_code=1, description=str(e))
    
    def _handle_insert(self, request: InsertRequest) -> BaseResult:
        """Handle insert request."""
        try:
            row_id = self.driver.insert(request.table_name, request.data)
            return SuccessResult(data={"row_id": row_id})
        except Exception as e:
            return ErrorResult(error_code=2, description=str(e))
    
    def _handle_select(self, request: SelectRequest) -> BaseResult:
        """Handle select request."""
        try:
            rows = self.driver.select(
                table_name=request.table_name,
                where=request.where,
                columns=request.columns,
                limit=request.limit,
                offset=request.offset,
                order_by=request.order_by
            )
            return DataResult(data=rows)
        except Exception as e:
            return ErrorResult(error_code=2, description=str(e))
    
    # ... all other unified RPC methods ...
```

**⚠️ CRITICAL:**
- RPC server **MUST use** BaseRequest and BaseResult classes
- All request handling **MUST** use concrete request classes
- All responses **MUST** return concrete result classes
- SQLite driver **MUST implement** all abstract methods from base classes

### Driver Module Structure

Each driver module should follow this structure:

```python
"""
PostgreSQL database driver implementation.

This driver implements BaseDatabaseDriver interface for PostgreSQL databases.
The driver works ONLY with tables - it does NOT know about objects (Project, File, etc.).

The RPC server (rpc_server.py) exposes unified RPC methods that call these
driver methods. Client library converts objects → tables before calling RPC.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseDatabaseDriver
from ..exceptions import (
    DriverError,
    DriverConnectionError,
    DriverTransactionError,
)

logger = logging.getLogger(__name__)


class PostgresDriver(BaseDatabaseDriver):
    """
    PostgreSQL database driver implementation.
    
    This driver works ONLY with tables:
    - insert(table_name, data_dict) - inserts row into table
    - select(table_name, where_dict) - selects rows from table
    - update(table_name, where_dict, data_dict) - updates rows in table
    - delete(table_name, where_dict) - deletes rows from table
    
    Driver does NOT know about Project, File, or any other objects.
    Client library converts objects → tables before calling RPC methods.
    """
    
    def __init__(self):
        """Initialize PostgreSQL driver."""
        self._connection = None
        self._transactions: Dict[str, Any] = {}
    
    @property
    def driver_type(self) -> str:
        """Return driver type identifier."""
        return "postgres"
    
    @property
    def is_thread_safe(self) -> bool:
        """PostgreSQL driver is thread-safe."""
        return True
    
    def connect(self, config: Dict[str, Any]) -> None:
        """
        Establish PostgreSQL connection.
        
        Args:
            config: Driver-specific configuration dictionary
                   (host, port, database, user, password, etc.)
        """
        # Implementation here
        pass
    
    def insert(self, table_name: str, data: Dict[str, Any]) -> int:
        """
        Insert row into table.
        
        Args:
            table_name: Name of table (e.g., "projects", "files")
            data: Dictionary with column names as keys and values
                 (e.g., {"id": "project-123", "name": "My Project"})
        
        Returns:
            Number of rows inserted (should be 1)
        """
        # Implementation here
        pass
    
    # ... implement all abstract methods ...
```

**⚠️ CRITICAL:**
- Driver methods work with **tables only** (table_name, data dict, where dict)
- Driver **does NOT** receive objects
- Driver **does NOT** know about object models
- All object → table conversion happens in client library

## Configuration

### Driver Configuration Schema

Each driver must accept configuration in this format:

```json
{
  "type": "postgres",
  "config": {
    "host": "localhost",
    "port": 5432,
    "database": "code_analysis",
    "user": "code_analysis",
    "password": "secret",
    "ssl_mode": "require",
    "connection_pool_size": 10,
    "connection_timeout": 30
  }
}
```

### Configuration Validation

Drivers must validate their configuration in `connect()` method:

```python
def connect(self, config: Dict[str, Any]) -> None:
    """Establish connection with configuration validation."""
    required_keys = ["host", "port", "database", "user", "password"]
    for key in required_keys:
        if key not in config:
            raise DriverConnectionError(f"Missing required config key: {key}")
    
    # Validate types
    if not isinstance(config["port"], int):
        raise DriverConnectionError("port must be integer")
    
    # Establish connection
    # ...
```

## Driver Registration

### Registering a Driver

Drivers must be registered in `code_analysis/core/database_driver_pkg/drivers/__init__.py`:

```python
from .base import BaseDatabaseDriver
from .sqlite import SQLiteDriver
from .postgres import PostgresDriver
from .mysql import MySQLDriver

# Driver registry
_DRIVERS: Dict[str, type[BaseDatabaseDriver]] = {
    "sqlite": SQLiteDriver,
    "postgres": PostgresDriver,
    "mysql": MySQLDriver,
}

def register_driver(name: str, driver_class: type[BaseDatabaseDriver]) -> None:
    """Register a new database driver."""
    if not issubclass(driver_class, BaseDatabaseDriver):
        raise TypeError("Driver class must be a subclass of BaseDatabaseDriver")
    _DRIVERS[name] = driver_class

def create_driver(driver_name: str, config: Dict[str, Any]) -> BaseDatabaseDriver:
    """Create driver instance."""
    if driver_name not in _DRIVERS:
        raise ValueError(f"Unknown driver type: {driver_name}")
    
    driver_class = _DRIVERS[driver_name]
    driver = driver_class()
    driver.connect(config["config"])
    return driver
```

## Error Handling

### Exception Classes

Drivers must use standard exception classes:

```python
# code_analysis/core/database_driver_pkg/exceptions.py

class DriverError(Exception):
    """Base exception for driver errors."""
    pass

class DriverConnectionError(DriverError):
    """Exception raised when connection fails."""
    pass

class DriverTransactionError(DriverError):
    """Exception raised when transaction operations fail."""
    pass

class DriverQueryError(DriverError):
    """Exception raised when query execution fails."""
    pass
```

### Error Handling Pattern

```python
def insert(self, table_name: str, data: Dict[str, Any]) -> int:
    """Insert row with proper error handling."""
    try:
        # Perform insert
        cursor.execute(...)
        return cursor.rowcount
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL insert failed: {e}")
        raise DriverQueryError(f"Insert failed: {e}") from e
```

## Data Type Mapping

### Standard Type Mapping

Drivers must map Python types to database types:

| Python Type | SQLite | PostgreSQL | MySQL |
|------------|--------|------------|-------|
| `str` | TEXT | VARCHAR/TEXT | VARCHAR/TEXT |
| `int` | INTEGER | INTEGER/BIGINT | INT/BIGINT |
| `float` | REAL | REAL/DOUBLE | FLOAT/DOUBLE |
| `bool` | INTEGER (0/1) | BOOLEAN | BOOLEAN/TINYINT |
| `datetime` | TEXT (ISO) | TIMESTAMP | DATETIME |
| `bytes` | BLOB | BYTEA | BLOB |
| `None` | NULL | NULL | NULL |

### Type Conversion

Drivers must handle type conversion in both directions:

```python
def _python_to_db_type(self, value: Any) -> Any:
    """Convert Python value to database type."""
    if isinstance(value, datetime):
        return value.isoformat()  # For SQLite
        # or: return value  # For PostgreSQL/MySQL with native support
    elif isinstance(value, bool):
        return 1 if value else 0  # For SQLite
        # or: return value  # For PostgreSQL/MySQL
    return value

def _db_to_python_type(self, value: Any, column_type: str) -> Any:
    """Convert database value to Python type."""
    # Implementation based on column type
    pass
```

## Transaction Management

### Transaction Lifecycle

Drivers must support transaction management:

1. **Begin**: `begin_transaction()` returns transaction ID
2. **Operations**: All operations use transaction ID
3. **Commit/Rollback**: `commit_transaction()` or `rollback_transaction()`

### Transaction Isolation

- Default isolation level should be appropriate for the database
- PostgreSQL: READ COMMITTED
- MySQL: REPEATABLE READ
- SQLite: SERIALIZABLE (default)

### Transaction Example

```python
# Begin transaction
tx_id = driver.begin_transaction()

try:
    # Perform operations
    driver.insert("projects", {...}, transaction_id=tx_id)
    driver.insert("files", {...}, transaction_id=tx_id)
    
    # Commit
    driver.commit_transaction(tx_id)
except Exception as e:
    # Rollback on error
    driver.rollback_transaction(tx_id)
    raise
```

## Schema Synchronization

### Schema Definition Format

Drivers must support schema definition in this format:

```python
schema_definition = {
    "tables": [
        {
            "name": "projects",
            "columns": [
                {"name": "id", "type": "TEXT", "primary_key": True},
                {"name": "root_path", "type": "TEXT", "nullable": False},
                {"name": "name", "type": "TEXT", "nullable": False},
                {"name": "updated_at", "type": "REAL"},
            ],
            "indexes": [
                {"name": "idx_projects_root_path", "columns": ["root_path"]},
            ],
        },
        # ... more tables ...
    ]
}
```

### Schema Sync Process

1. **Backup** (if backup_dir provided)
2. **Compare** existing schema with definition
3. **Create** missing tables
4. **Modify** existing tables (add columns, indexes)
5. **Report** changes made

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests

- [ ] Test all interface methods
- [ ] Test connection/disconnection
- [ ] Test table operations (create, drop)
- [ ] Test CRUD operations (insert, update, delete, select)
- [ ] Test transactions (begin, commit, rollback)
- [ ] Test schema operations
- [ ] Test error handling
- [ ] **Coverage: 90%+ for all driver code**

### Integration Tests with Real Database

- [ ] **Test with real database instance**
- [ ] Test all operations on real database
- [ ] Test transactions on real database
- [ ] Test schema sync on real database
- [ ] Test concurrent operations
- [ ] Test connection pooling (if applicable)

**Real Database Test Requirements**:
- [ ] Use actual database server (PostgreSQL, MySQL, etc.)
- [ ] Test with real database schema
- [ ] Test with real data
- [ ] Verify all operations work correctly

### Integration Tests with Real Server

- [ ] **Test driver through real running server**
- [ ] Test RPC communication with real server
- [ ] Test all RPC methods through real server
- [ ] Test error scenarios with real server

### Performance Tests

- [ ] Test connection performance
- [ ] Test query performance
- [ ] Test transaction performance
- [ ] Test concurrent request handling
- [ ] Benchmark against SQLite driver

## Test Structure

### Test Files

```
tests/test_drivers/
├── __init__.py
├── test_base_driver.py          # Base interface tests
├── test_postgres_driver.py      # PostgreSQL driver tests
│   ├── test_connection.py
│   ├── test_crud_operations.py
│   ├── test_transactions.py
│   └── test_schema_sync.py
├── test_mysql_driver.py         # MySQL driver tests
└── conftest.py                   # Test fixtures
```

### Test Example

```python
"""
Tests for PostgreSQL driver with real database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from code_analysis.core.database_driver_pkg.drivers.postgres import PostgresDriver
from code_analysis.core.database_driver_pkg.exceptions import DriverError

@pytest.fixture
def postgres_config():
    """PostgreSQL test configuration."""
    return {
        "host": "localhost",
        "port": 5432,
        "database": "code_analysis_test",
        "user": "test_user",
        "password": "test_password",
    }

@pytest.fixture
def postgres_driver(postgres_config):
    """Create PostgreSQL driver instance."""
    driver = PostgresDriver()
    driver.connect(postgres_config)
    yield driver
    driver.disconnect()

class TestPostgresDriverConnection:
    """Test PostgreSQL driver connection."""
    
    def test_connect_success(self, postgres_config):
        """Test successful connection."""
        driver = PostgresDriver()
        driver.connect(postgres_config)
        assert driver._connection is not None
        driver.disconnect()
    
    def test_connect_invalid_config(self):
        """Test connection with invalid config."""
        driver = PostgresDriver()
        with pytest.raises(DriverError):
            driver.connect({"invalid": "config"})

class TestPostgresDriverCRUD:
    """Test PostgreSQL driver CRUD operations."""
    
    def test_insert(self, postgres_driver):
        """Test insert operation."""
        result = postgres_driver.insert(
            "projects",
            {"id": "test-id", "name": "Test Project", "root_path": "/test"}
        )
        assert result == 1
    
    def test_select(self, postgres_driver):
        """Test select operation."""
        # Insert test data
        postgres_driver.insert("projects", {...})
        
        # Select
        results = postgres_driver.select("projects", where={"id": "test-id"})
        assert len(results) == 1
        assert results[0]["name"] == "Test Project"
```

## Documentation Requirements

### Driver Documentation

Each driver must include:

1. **Module docstring**: Description of driver
2. **Class docstring**: Description of driver class
3. **Method docstrings**: All methods must have docstrings
4. **Configuration documentation**: Document all config options
5. **Example usage**: Provide usage examples

### Example Documentation

```python
"""
PostgreSQL database driver for driver process.

This driver implements the BaseDatabaseDriver interface for PostgreSQL databases.
It supports all standard database operations including transactions and schema
synchronization.

Configuration:
    host (str): PostgreSQL server hostname (required)
    port (int): PostgreSQL server port (default: 5432)
    database (str): Database name (required)
    user (str): Database user (required)
    password (str): Database password (required)
    ssl_mode (str): SSL mode (default: "prefer")
    connection_pool_size (int): Connection pool size (default: 10)

Example:
    >>> config = {
    ...     "host": "localhost",
    ...     "port": 5432,
    ...     "database": "code_analysis",
    ...     "user": "code_analysis",
    ...     "password": "secret"
    ... }
    >>> driver = PostgresDriver()
    >>> driver.connect(config)
    >>> driver.insert("projects", {"id": "test", "name": "Test"})
    1
    >>> driver.disconnect()

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""
```

## Code Quality Requirements

### Code Style

- Follow PEP 8
- Use type hints for all methods
- Use docstrings for all classes and methods
- Maximum file size: 400 lines (split if needed)

### Linting

- Run `black` for code formatting
- Run `flake8` for style checking
- Run `mypy` for type checking
- **All errors must be fixed**

### Code Organization

- One class per file (except exceptions, enums)
- Split large classes into facade + smaller classes
- Keep files under 400 lines

## RPC Method Implementation

### RPC Server Implementation

The RPC server (`rpc_server.py`) must implement the unified interface:

```python
class DatabaseDriverRPCServer:
    """
    RPC server with unified interface.
    
    All drivers (SQLite, PostgreSQL, MySQL) expose the same RPC methods.
    The server calls driver implementation methods internally.
    """
    
    def __init__(self, driver: BaseDatabaseDriver):
        """Initialize with driver implementation."""
        self.driver = driver
    
    # Unified RPC methods - MUST be identical for all drivers
    def create_table(self, schema: dict) -> bool:
        """RPC: Create table from schema."""
        return self.driver.create_table(schema)
    
    def insert(self, table_name: str, data: dict) -> int:
        """RPC: Insert row into table."""
        return self.driver.insert(table_name, data)
    
    def select(
        self,
        table_name: str,
        where: Optional[dict] = None,
        columns: Optional[list] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[list] = None
    ) -> list[dict]:
        """RPC: Select rows from table."""
        return self.driver.select(
            table_name=table_name,
            where=where,
            columns=columns,
            limit=limit,
            offset=offset,
            order_by=order_by
        )
    
    # ... all other unified RPC methods ...
```

**⚠️ CRITICAL:**
- RPC methods are **unified** - same for all drivers
- RPC methods work with **tables only** (table_name, data, where)
- RPC server calls driver implementation methods
- Driver implementation can differ (SQLite vs PostgreSQL), but RPC interface is identical

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout driver development**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing driver code using `code_mapper` indexes in `code_analysis/` directory
- [ ] Review existing driver implementations (SQLite, etc.)
- [ ] Check for existing RPC server patterns
- [ ] Use command: `code_mapper -r code_analysis/` (excludes tests and test_data)

### During Code Implementation
- [ ] **Run code_mapper after each block of changes** to update indexes
- [ ] Use command: `code_mapper -r code_analysis/` to update indexes
- [ ] Keep indexes up-to-date for other developers and tools

### After Writing Code (Production Code Only, Not Tests)
- [ ] **⚠️ CRITICAL: Run code_mapper** to check for errors and issues
- [ ] **Command**: `code_mapper -r code_analysis/` (excludes tests and test_data from analysis)
- [ ] **Eliminate ALL errors** found by code_mapper utility - this is MANDATORY
- [ ] Fix all code quality issues detected by code_mapper
- [ ] Verify no duplicate code was introduced
- [ ] Check file sizes (must be < 400 lines)
- [ ] Split files if they exceed 400 lines
- [ ] **DO NOT proceed until ALL code_mapper errors are fixed**

**⚠️ IMPORTANT**: 
- Always use `code_mapper -r code_analysis/` to exclude tests and test_data
- After writing production code, you MUST run code_mapper and fix ALL errors
- Test files are excluded from code_mapper analysis
- All production code errors must be eliminated before proceeding

**Commands**:
```bash
# Check existing functionality (excludes tests and test_data)
code_mapper -r code_analysis/

# Update indexes after changes (excludes tests and test_data)
code_mapper -r code_analysis/
```

## Implementation Checklist

When implementing a new driver, follow this checklist:

### Setup
- [ ] Create driver module file
- [ ] Import BaseDatabaseDriver
- [ ] Create driver class inheriting from BaseDatabaseDriver
- [ ] Register driver in `__init__.py`

### Core Implementation
- [ ] Implement `driver_type` property
- [ ] Implement `is_thread_safe` property
- [ ] Implement `connect()` method
- [ ] Implement `disconnect()` method
- [ ] **Implement all abstract methods from BaseRequest classes**
- [ ] **Implement all abstract methods from BaseResult classes**
- [ ] **Use concrete request classes (InsertRequest, SelectRequest, etc.) in RPC handlers**
- [ ] **Return concrete result classes (SuccessResult, ErrorResult, etc.) from RPC methods**
- [ ] Implement `create_table()` method (table-level)
- [ ] Implement `drop_table()` method (table-level)
- [ ] Implement `insert()` method (table-level: table_name, data dict)
- [ ] Implement `update()` method (table-level: table_name, where dict, data dict)
- [ ] Implement `delete()` method (table-level: table_name, where dict)
- [ ] Implement `select()` method (table-level: table_name, where dict, etc.)
- [ ] Implement `execute()` method (raw SQL)
- [ ] Implement `begin_transaction()` method
- [ ] Implement `commit_transaction()` method
- [ ] Implement `rollback_transaction()` method
- [ ] Implement `get_table_info()` method (table-level)
- [ ] Implement `sync_schema()` method (table-level)

**⚠️ CRITICAL:**
- All methods work with **tables only** (table_name, data dict, where dict)
- **DO NOT** implement object-level methods (create_project, get_file, etc.)
- **DO NOT** accept objects (Project, File, etc.) as parameters
- Object → table conversion happens in client library, NOT in driver
- **MUST use BaseRequest and BaseResult classes** - extend them, don't create new ones
- **MUST implement all abstract methods** from base classes

### Error Handling
- [ ] Use standard exception classes
- [ ] Handle connection errors
- [ ] Handle query errors
- [ ] Handle transaction errors
- [ ] Log all errors appropriately

### Testing
- [ ] Write unit tests (90%+ coverage)
- [ ] Write integration tests with real database
- [ ] Write integration tests with real server
- [ ] Run all tests and fix errors
- [ ] Verify 90%+ coverage

### Documentation
- [ ] Write module docstring
- [ ] Write class docstring
- [ ] Write method docstrings
- [ ] Document configuration options
- [ ] Provide usage examples

### Code Quality
- [ ] Run `black` and fix formatting
- [ ] Run `flake8` and fix errors
- [ ] Run `mypy` and fix type errors
- [ ] Verify file size < 400 lines
- [ ] Review code structure

## Reference Implementation

See `code_analysis/core/database_driver_pkg/drivers/sqlite.py` for reference implementation of SQLite driver.

**Key Points from Reference:**
- Driver works ONLY with tables (table_name, data dict, where dict)
- Driver does NOT know about objects (Project, File, etc.)
- RPC server exposes unified interface
- Client library performs object ↔ table conversion

## Summary: Driver Architecture

### What Driver IS:
✅ RPC server with unified interface  
✅ Works with tables only (table_name, data, where)  
✅ Implements BaseDatabaseDriver interface internally  
✅ Runs in separate process  

### What Driver IS NOT:
❌ Object-oriented API (that's client library)  
❌ Knowledge of Project, File, or other objects  
❌ Object → table conversion (that's client library)  
❌ Different RPC interface per driver (interface is unified)  

### What Client Library IS:
✅ Object-oriented API (Project, File, etc.)  
✅ Object ↔ table conversion  
✅ RPC client communication  
✅ Used by workers and commands  

### What Client Library IS NOT:
❌ Database driver implementation  
❌ Direct database access  
❌ Table-level operations (users don't see tables)

## Support

For questions or issues with driver development, refer to:
- [Technical Specification](../DATABASE_DRIVER_RPC_REFACTORING.md)
- [Step 3: Driver Process Implementation](./STEP_03_DRIVER_PROCESS.md)
- [Unified Testing Pipeline](./STEP_15_TESTING_PIPELINE.md)
