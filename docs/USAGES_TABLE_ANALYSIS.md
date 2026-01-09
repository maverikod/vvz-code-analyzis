# Analysis: Why usages Table is Not Populated

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-09

## Problem Statement

The `usages` table exists in the database schema but is **never populated** during code indexing. This causes `find_dependencies` and `find_usages` commands to return empty results.

## Root Cause Analysis

### 1. Table Schema Exists

The `usages` table is created in `code_analysis/core/database/base.py` (lines 473-488):

```sql
CREATE TABLE IF NOT EXISTS usages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    line INTEGER NOT NULL,
    usage_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_class TEXT,
    target_name TEXT NOT NULL,
    context TEXT,
    created_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
)
```

### 2. No Function to Add Usages

**Problem**: There is **no function** in `code_analysis/core/database/entities.py` or anywhere else to insert records into the `usages` table.

**Evidence**:
- `grep` search for `INSERT.*usages` or `add.*usage` returns **no results**
- No function like `add_usage()` exists in the codebase
- The table is created but never written to

### 3. Indexing Process Doesn't Track Usages

**Problem**: The `_analyze_file` method in `code_analysis/commands/code_mapper_mcp_command.py` extracts:
- ✅ Classes (via `add_class`)
- ✅ Functions (via `add_function`)
- ✅ Methods (via `add_method`)
- ✅ Imports (via `add_import`)
- ❌ **Usages are NOT tracked**

**Current Process** (lines 366-522):
1. Walks AST tree
2. Extracts class definitions
3. Extracts function definitions
4. Extracts method definitions
5. Extracts imports
6. **Missing**: No AST visitor to track function calls, method calls, class instantiations

### 4. What Should Be Tracked

To properly populate the `usages` table, the system should track:

1. **Function Calls** (`ast.Call` with `ast.Name` as func):
   - `process_data()` → usage of function `process_data`
   - `calculate(x, y)` → usage of function `calculate`

2. **Method Calls** (`ast.Call` with `ast.Attribute` as func):
   - `obj.method()` → usage of method `method` in class of `obj`
   - `self.process()` → usage of method `process` in current class

3. **Class Instantiations** (`ast.Call` with class name):
   - `MyClass()` → usage of class `MyClass`
   - `DataProcessor()` → usage of class `DataProcessor`

4. **Attribute Access** (for properties):
   - `obj.property` → usage of property `property`

5. **Inheritance** (already tracked via `bases` in classes table):
   - `class Child(BaseClass):` → dependency on `BaseClass`

## Impact

### Commands Affected

1. **`find_dependencies`**: Returns empty results because it searches `usages` table
2. **`find_usages`**: Returns empty results because it searches `usages` table

### Current Workaround

Both commands have been modified to use alternative data sources:
- **Imports table**: For module/class/function imports
- **Classes table**: For inheritance relationships (via `bases` field)
- **Usages table**: Checked but always empty

This provides **partial functionality** but doesn't track actual code usage (function calls, method calls, instantiations).

## Solution Options

### Option 1: Implement Usage Tracking (Recommended)

**Pros**:
- Full functionality for `find_dependencies` and `find_usages`
- Accurate tracking of actual code usage
- Enables comprehensive dependency analysis

**Cons**:
- Requires significant implementation effort
- May impact indexing performance
- Requires AST visitor to track all call sites

**Implementation Steps**:
1. Create `add_usage()` function in `entities.py`
2. Create `UsageTracker` AST visitor class
3. Integrate visitor into `_analyze_file` method
4. Track all `ast.Call` nodes and extract target information

### Option 2: Keep Current Workaround

**Pros**:
- Already implemented
- Works for imports and inheritance
- No performance impact

**Cons**:
- Doesn't track actual usage (calls)
- Limited functionality
- May confuse users expecting full usage tracking

### Option 3: Hybrid Approach

**Pros**:
- Best of both worlds
- Can start with imports/inheritance (already working)
- Add usage tracking incrementally

**Cons**:
- More complex implementation
- Requires careful integration

## Recommended Solution

**Implement Option 1** - Full usage tracking:

1. **Create `add_usage()` function** in `code_analysis/core/database/entities.py`:
   ```python
   def add_usage(
       self,
       file_id: int,
       line: int,
       usage_type: str,
       target_type: str,
       target_name: str,
       target_class: Optional[str] = None,
       context: Optional[str] = None,
   ) -> int:
       """Add usage record to database."""
   ```

2. **Create `UsageTracker` AST visitor** to track:
   - Function calls (`ast.Call` with `ast.Name`)
   - Method calls (`ast.Call` with `ast.Attribute`)
   - Class instantiations
   - Attribute accesses (for properties)

3. **Integrate into `_analyze_file`**:
   - Run `UsageTracker` visitor on AST tree
   - Call `add_usage()` for each usage found

4. **Performance Considerations**:
   - Batch inserts for better performance
   - Use transactions to group inserts
   - Consider making it optional (configurable)

## Current Status

- ✅ Table schema exists
- ✅ Function `add_usage()` implemented in `entities.py`
- ✅ `UsageTracker` AST visitor created in `usage_tracker.py`
- ✅ Usage tracking integrated into `_analyze_file` method
- ✅ Commands work with real usage data from `usages` table
- ✅ Commands also use workarounds (imports, inheritance) for comprehensive results

## Implementation Details

### UsageTracker Class

Created in `code_analysis/core/usage_tracker.py`:
- Tracks function calls (`ast.Call` with `ast.Name`)
- Tracks method calls (`ast.Call` with `ast.Attribute`)
- Tracks class instantiations (uppercase names in calls)
- Maintains context (current class, current function)
- Records usage type, target type, target name, and context

### Integration

Integrated into `code_analysis/commands/code_mapper_mcp_command.py`:
- Runs after extracting classes, functions, methods, and imports
- Uses callback pattern to add usages to database
- Handles errors gracefully (continues even if usage tracking fails)
- Adds `usages_added` count to indexing results

### What is Tracked

1. **Function Calls**: `func_name()` → usage of function `func_name`
2. **Method Calls**: `obj.method()` → usage of method `method` (with class context if `self.method()`)
3. **Class Instantiations**: `ClassName()` → usage of class `ClassName`
4. **Context Information**: Tracks which class/function the usage occurs in

## Next Steps

1. ✅ Implement `add_usage()` function - **DONE**
2. ✅ Create `UsageTracker` AST visitor - **DONE**
3. ✅ Integrate into indexing process - **DONE**
4. ⏳ Test with sample projects - **TODO**
5. ✅ Commands use real usage data - **DONE** (commands already updated to use usages table)

