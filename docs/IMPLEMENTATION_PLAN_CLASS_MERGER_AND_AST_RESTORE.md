# Technical Specification: ClassMerger and AST/CST File Restoration

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-01-28  
**Status**: Draft

## Executive Summary

This document provides a detailed step-by-step implementation plan for two features:

1. **ClassMerger**: Merge multiple classes into a single class (inverse operation of ClassSplitter)
2. **File Restoration from AST/CST**: Enhance file restoration capabilities using AST/CST trees stored in database

## Table of Contents

1. [ClassMerger Implementation](#1-classmerger-implementation)
2. [File Restoration from AST/CST](#2-file-restoration-from-astcst)
3. [Testing Strategy](#3-testing-strategy)
4. [Integration Points](#4-integration-points)

---

## 1. ClassMerger Implementation

### 1.1 Overview

**Purpose**: Merge multiple classes (that were previously split) back into a single class.

**Inverse Operation**: This is the inverse of `ClassSplitter.split_class()` which splits one class into multiple classes.

**Use Cases**:
- Undo a class split operation
- Consolidate related classes that were split but should be together
- Refactor code structure by merging classes

### 1.2 Current State Analysis

**Existing Code**:
- `ClassSplitter` (`code_analysis/core/refactorer_pkg/splitter.py`) - splits one class into multiple
- `SuperclassExtractor` (`code_analysis/core/refactorer_pkg/extractor.py`) - extracts common functionality
- `BaseRefactorer` (`code_analysis/core/refactorer_pkg/base.py`) - base class with common functionality

**Key Observations from ClassSplitter**:
1. Split creates multiple destination classes from one source class
2. Original class is modified to contain wrapper methods that delegate to destination classes
3. Properties are moved to destination classes and accessed via instance attributes
4. Docstrings are preserved in destination classes
5. Validation ensures completeness (all original methods/properties are present)

**What ClassMerger Must Do**:
1. Merge multiple source classes into one destination class
2. Combine all methods from source classes
3. Merge properties (handle conflicts)
4. Preserve docstrings (merge or choose one)
5. Remove wrapper methods and inline actual implementations
6. Validate merged class is complete

### 1.3 Configuration Format

**Input Configuration**:
```python
{
    "src_classes": ["Class1", "Class2", "Class3"],  # Classes to merge
    "dst_class": "MergedClass",  # Name of resulting class
    "merge_strategy": "combine" | "override" | "custom",  # How to handle conflicts
    "property_conflicts": {  # Optional: manual property conflict resolution
        "prop1": "Class1",  # Use prop1 from Class1
        "prop2": "Class2"   # Use prop2 from Class2
    },
    "method_conflicts": {  # Optional: manual method conflict resolution
        "method1": "Class1",  # Use method1 from Class1
        "method2": "Class2"   # Use method2 from Class2
    },
    "docstring_strategy": "first" | "merge" | "custom",  # How to handle docstrings
    "preserve_wrappers": False  # If True, keep wrapper methods; if False, inline them
}
```

### 1.4 Step-by-Step Implementation Plan

#### Step 1.1: Create ClassMerger Class Structure

**File**: `code_analysis/core/refactorer_pkg/merger.py`

**Tasks**:
1. Create `ClassMerger` class inheriting from `BaseRefactorer`
2. Implement `__init__` method (inherited from base)
3. Add class-level docstring
4. Define method signatures (stubs with `raise NotImplementedError`)

**Code Structure**:
```python
"""
Module merger.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from .base import BaseRefactorer
try:
    from .formatters import format_code_with_black, format_error_message
except ImportError:
    from .utils import format_code_with_black, format_error_message

logger = logging.getLogger(__name__)


class ClassMerger(BaseRefactorer):
    """Class for merging multiple classes into a single class."""
    
    def merge_classes(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Merge multiple classes into a single class.
        
        Args:
            config: Merge configuration
            
        Returns:
            Tuple of (success, message)
        """
        raise NotImplementedError
```

#### Step 1.2: Implement Configuration Validation

**Method**: `validate_merge_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]`

**Tasks**:
1. Validate `src_classes` list is not empty
2. Validate all source classes exist in file
3. Validate `dst_class` name is valid Python identifier
4. Validate no conflicts in class names (src_classes don't include dst_class)
5. Check for method name conflicts between source classes
6. Check for property name conflicts between source classes
7. Validate merge_strategy is one of allowed values
8. Return (is_valid, list_of_errors)

**Validation Rules**:
- At least 2 source classes required
- All source classes must exist in file
- Destination class name must be valid identifier
- If `merge_strategy` is "override", conflicts are allowed (first class wins)
- If `merge_strategy` is "combine", conflicts must be resolved manually
- If `merge_strategy` is "custom", `property_conflicts` and `method_conflicts` must be provided

**Error Messages**:
- "Source classes list is empty"
- "Class '{name}' not found in file"
- "Invalid destination class name: '{name}'"
- "Method '{name}' exists in multiple source classes: {classes}"
- "Property '{name}' exists in multiple source classes: {classes}"

#### Step 1.3: Implement Class Discovery and Analysis

**Method**: `_analyze_source_classes(src_classes: List[str]) -> Dict[str, ast.ClassDef]`

**Tasks**:
1. Find all source class AST nodes
2. Extract class metadata:
   - Class name
   - Base classes
   - Docstring
   - Methods (with signatures)
   - Properties (from __init__)
   - Nested classes
3. Return dictionary mapping class name to AST node

**Return Structure**:
```python
{
    "Class1": {
        "node": ast.ClassDef,
        "methods": ["method1", "method2"],
        "properties": ["prop1", "prop2"],
        "docstring": "...",
        "bases": ["BaseClass"],
        "nested_classes": []
    },
    ...
}
```

#### Step 1.4: Implement Conflict Detection

**Method**: `_detect_conflicts(source_classes: Dict[str, ast.ClassDef]) -> Dict[str, Any]`

**Tasks**:
1. Detect method name conflicts (same method in multiple classes)
2. Detect property name conflicts (same property in multiple classes)
3. Detect base class conflicts (different inheritance hierarchies)
4. Return conflict report

**Return Structure**:
```python
{
    "method_conflicts": {
        "method1": ["Class1", "Class2"],  # method1 exists in both
        ...
    },
    "property_conflicts": {
        "prop1": ["Class1", "Class3"],
        ...
    },
    "base_conflicts": {
        "Class1": ["Base1"],
        "Class2": ["Base2"],  # Different bases
        ...
    }
}
```

#### Step 1.5: Implement Merge Strategy Logic

**Method**: `_resolve_conflicts(conflicts: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, str]`

**Tasks**:
1. Apply merge strategy:
   - "combine": Require manual resolution (raise error if conflicts exist)
   - "override": First class wins (automatic resolution)
   - "custom": Use provided `property_conflicts` and `method_conflicts`
2. Return resolution mapping: `{"method1": "Class1", "prop1": "Class2", ...}`

**Logic**:
- If "override": For each conflict, use first occurrence (first class in src_classes list)
- If "combine": Raise error listing all conflicts
- If "custom": Use provided mappings, validate all conflicts are resolved

#### Step 1.6: Implement Merged Class Construction

**Method**: `_build_merged_class_ast(
    dst_class_name: str,
    source_classes: Dict[str, ast.ClassDef],
    conflict_resolution: Dict[str, str],
    config: Dict[str, Any]
) -> ast.ClassDef`

**Tasks**:
1. Determine base classes (merge all unique bases from source classes)
2. Merge docstrings (based on `docstring_strategy`):
   - "first": Use first class docstring
   - "merge": Combine all docstrings
   - "custom": Use provided docstring
3. Merge properties:
   - Collect all properties from all source classes
   - Resolve conflicts using `conflict_resolution`
   - Build combined `__init__` method
4. Merge methods:
   - Collect all methods from all source classes
   - Resolve conflicts using `conflict_resolution`
   - Remove wrapper methods if `preserve_wrappers=False`
   - Inline actual implementations
5. Merge nested classes (if any)
6. Return merged class AST node

**Property Merging Logic**:
- Collect all `self.attr = value` assignments from all `__init__` methods
- If conflict: use resolved class's property
- Combine into single `__init__` method

**Method Merging Logic**:
- Collect all methods from all source classes
- If conflict: use resolved class's method
- If wrapper method detected (delegates to another class):
  - If `preserve_wrappers=False`: Find actual implementation and inline it
  - If `preserve_wrappers=True`: Keep wrapper
- Preserve method decorators and type hints

#### Step 1.7: Implement Source Code Generation

**Method**: `_perform_merge(
    source_classes: Dict[str, ast.ClassDef],
    config: Dict[str, Any]
) -> str`

**Tasks**:
1. Detect conflicts
2. Resolve conflicts using strategy
3. Build merged class AST
4. Replace source classes with merged class in file
5. Remove original source classes
6. Return new file content

**File Modification Logic**:
1. Find positions of all source classes in file
2. Determine "before" and "after" sections
3. Generate merged class code
4. Replace source classes section with merged class
5. Preserve file-level code (imports, top-level functions, etc.)

**Code Structure**:
```python
# Before section (imports, top-level code before first source class)
# Merged class
# After section (code after last source class)
```

#### Step 1.8: Implement Validation

**Method**: `_validate_merge_completeness(
    original_classes: Dict[str, ast.ClassDef],
    merged_class: ast.ClassDef,
    config: Dict[str, Any]
) -> Tuple[bool, Optional[str]]`

**Tasks**:
1. Verify all methods from source classes are in merged class
2. Verify all properties from source classes are in merged class
3. Verify docstrings are preserved (if required)
4. Return (is_complete, error_message)

**Completeness Checks**:
- All methods from all source classes must be present
- All properties from all source classes must be present
- No methods/properties should be lost during merge

#### Step 1.9: Implement Main Merge Method

**Method**: `merge_classes(config: Dict[str, Any]) -> Tuple[bool, Optional[str]]`

**Tasks**:
1. Create backup (via `self.create_backup()`)
2. Load file (via `self.load_file()`)
3. Validate configuration
4. Analyze source classes
5. Perform merge
6. Write new content to file
7. Format code with black
8. Validate Python syntax
9. Validate merge completeness
10. Validate docstrings (if required)
11. Return (success, message)

**Error Handling**:
- If any step fails: restore backup and return error
- Log all errors with context
- Provide detailed error messages

#### Step 1.10: Implement Preview Method

**Method**: `preview_merge(config: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]`

**Tasks**:
1. Load file
2. Validate configuration
3. Analyze source classes
4. Perform merge (without writing to file)
5. Format result with black
6. Return (success, error_message, preview_content)

**Use Case**: Allow user to preview merge before applying it.

#### Step 1.11: Add to RefactorCommand

**File**: `code_analysis/commands/refactor.py`

**Tasks**:
1. Import `ClassMerger`
2. Add `merge_classes` method to `RefactorCommand` class
3. Follow same pattern as `split_class`, `extract_superclass`, `split_file_to_package`

**Method Signature**:
```python
async def merge_classes(
    self, root_dir: str, file_path: str, config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Merge multiple classes into a single class.
    
    Args:
        root_dir: Root directory of the project
        file_path: Path to Python file
        config: Merge configuration
        
    Returns:
        Dictionary with success status and message
    """
```

#### Step 1.12: Create MCP Command

**File**: `code_analysis/commands/refactor_mcp_commands.py`

**Tasks**:
1. Add `MergeClassesMCPCommand` class
2. Follow same pattern as `SplitClassMCPCommand`
3. Register command in `hooks.py`

**Command Name**: `merge_classes`

**Parameters**:
- `root_dir`: Project root directory
- `file_path`: Path to Python file
- `config`: Merge configuration (JSON)

**Response**:
```json
{
    "success": true,
    "message": "Classes merged successfully",
    "project_id": "..."
}
```

### 1.5 Edge Cases and Error Handling

**Edge Cases**:
1. **Empty source classes list**: Return error
2. **Class not found**: Return error with class name
3. **Method conflicts with different signatures**: 
   - If "override": Use first class's method
   - If "combine": Return error requiring manual resolution
4. **Property conflicts with different types**:
   - Same as method conflicts
5. **Circular dependencies**: 
   - Check if merged class would create circular imports
6. **Nested classes**: 
   - Merge nested classes if they exist in source classes
7. **Class decorators**: 
   - Preserve decorators from first class (or merge if compatible)
8. **Type hints conflicts**: 
   - Use first class's type hints (or merge if compatible)

**Error Messages**:
- Clear, actionable error messages
- Include file path and line numbers where possible
- Suggest solutions (e.g., "Use merge_strategy='override' to automatically resolve")

### 1.6 Testing Requirements

**Unit Tests**:
1. Test configuration validation
2. Test conflict detection
3. Test conflict resolution strategies
4. Test merged class construction
5. Test completeness validation

**Integration Tests**:
1. Test full merge workflow
2. Test with real Python files
3. Test error handling and backup restoration
4. Test with various merge strategies

**Test Files**:
- `tests/test_merger.py` - Unit tests
- `test_data/merge_test_cases/` - Test case files

---

## 2. File Restoration from AST/CST

### 2.1 Overview

**Purpose**: Restore file content from AST or CST trees stored in database when file is missing from filesystem.

**Current State**:
- ✅ CST restoration is **already implemented** in `_restore_file_from_cst()` method
- ✅ CST trees are saved to database (`cst_trees` table)
- ⚠️ AST restoration is **partially feasible** with comment preservation approach
- ✅ Project has `_parse_with_comments()` method that preserves comments in AST

**Key Finding**: AST trees **can be restored** with important information preserved:
- ✅ **Comments can be preserved** using `_parse_with_comments()` method
- ✅ **Docstrings are preserved** in AST (standard behavior)
- ❌ Formatting is lost (not critical per user requirements)
- ✅ Comments can be converted to docstrings during restoration

**Approach**: 
1. **Save AST with comments**: Use `_parse_with_comments()` when saving AST to database
2. **Restore from AST**: Convert comment nodes to docstrings during restoration
3. **Use CST as primary**: CST restoration remains primary method (preserves everything)
4. **AST as fallback**: AST restoration as fallback when CST is not available

**User Requirements**:
- Formatting is **not critical** (can be reformatted with black)
- **Comments and docstrings are critical** (must be preserved)
- Comments can be represented as docstrings if needed

### 2.2 Current Implementation Analysis

**File**: `code_analysis/commands/file_management.py`

**Method**: `_restore_file_from_cst()` (lines 606-655)

**Current Implementation**:
```python
async def _restore_file_from_cst(
    self, file_id: int, file_path: str, file_record: Dict[str, Any]
) -> bool:
    """
    Restore file from CST (source code stored in database).
    """
    # Get CST tree (source code) from database
    cst_data = await self.database.get_cst_tree(file_id)
    if not cst_data:
        logger.warning(f"No CST tree (source code) found for file {file_id}")
        return False

    cst_code = cst_data.get("cst_code")
    if not cst_code:
        logger.warning(f"CST tree has no source code for file {file_id}")
        return False

    # Determine target path
    if file_record.get("deleted"):
        # Restore to version directory
        version_path = Path(self.version_dir) / file_record.get("version_dir", "") / file_path
        target_path = version_path
    else:
        # Restore to project directory
        target_path = self.root_dir / file_path

    # Restore file content
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(cst_code, encoding="utf-8")

    logger.info(f"Restored file {file_path} from CST to {target_path}")
    return True
```

**Status**: ✅ **Already implemented and working**

### 2.3 Enhancement Plan

**Primary Approach**: Enhance AST restoration with comment preservation

1. **Update AST saving**: Use `_parse_with_comments()` when saving AST to database
2. **Implement AST restoration**: Restore file from AST with comments converted to docstrings
3. **Enhance CST restoration** (if needed):
   - Add validation that restored file is valid Python
   - Add option to restore from specific CST version (by hash)
   - Add logging for restoration operations
4. **Update documentation**: Document both AST and CST restoration approaches

### 2.4 Step-by-Step Enhancement Plan

#### Step 2.1: Update AST Saving to Preserve Comments

**File**: `code_analysis/commands/code_mapper_mcp_command.py`

**Current Code** (line 233):
```python
tree = ast.parse(file_content, filename=str(file_path))
```

**New Code**:
```python
# Use _parse_with_comments to preserve comments in AST
from ..core.refactorer_pkg.base import BaseRefactorer

# Create temporary refactorer instance to use _parse_with_comments
temp_refactorer = BaseRefactorer(file_path)
temp_refactorer.original_content = file_content
tree = temp_refactorer._parse_with_comments(file_content)
```

**Alternative Approach** (better - extract method):
1. Extract `_parse_with_comments` logic to utility function
2. Use utility function in `update_indexes`

**File**: `code_analysis/core/ast_utils.py` (NEW FILE)

**Tasks**:
1. Create utility module for AST operations
2. Extract `_parse_with_comments` logic to standalone function
3. Make it reusable across codebase

**Code Structure**:
```python
"""
AST utilities for parsing with comment preservation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import tokenize
import io
from typing import Dict, List, Tuple


def parse_with_comments(source: str, filename: str = "<unknown>") -> ast.Module:
    """
    Parse Python code and preserve comments as string expressions in AST.
    
    Comments are added as ast.Expr(ast.Constant(value="# comment")) nodes
    before the statements they precede.
    
    Args:
        source: Python source code string
        filename: Filename for error messages
        
    Returns:
        AST module with comments preserved as string expressions
    """
    # First, parse normally
    tree = ast.parse(source, filename=filename)
    
    # Extract comments using tokenize
    comments_map: Dict[int, List[Tuple[int, str]]] = {}
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        for token in tokens:
            if token.type == tokenize.COMMENT:
                line_num = token.start[0]
                col = token.start[1]
                comment_text = token.string.strip()
                if line_num not in comments_map:
                    comments_map[line_num] = []
                comments_map[line_num].append((col, comment_text))
    except Exception:
        # If comment extraction fails, return tree without comments
        return tree
    
    # Add comments to AST as string expressions
    # ... (rest of logic from BaseRefactorer._parse_with_comments)
    
    return tree
```

#### Step 2.2: Implement AST Restoration with Comment-to-Docstring Conversion

**File**: `code_analysis/commands/file_management.py`

**New Method**: `_restore_file_from_ast()`

**Tasks**:
1. Get AST tree from database
2. Deserialize AST JSON to AST node
3. Convert comment nodes to docstrings
4. Use `ast.unparse()` to generate code
5. Format with black
6. Write to file

**Method Signature**:
```python
async def _restore_file_from_ast(
    self, file_id: int, file_path: str, file_record: Dict[str, Any]
) -> bool:
    """
    Restore file from AST tree with comments converted to docstrings.
    
    Args:
        file_id: File ID
        file_path: File path
        file_record: File record from database
        
    Returns:
        True if file was restored, False otherwise
    """
```

**Implementation Steps**:
1. Get AST tree from database: `database.get_ast_tree(file_id)`
2. Deserialize AST JSON: `ast.loads(ast_json)` or reconstruct from JSON
3. Process AST to convert comments:
   - Find all `ast.Expr(ast.Constant(value="# comment"))` nodes
   - Convert to docstrings before functions/classes
   - Remove comment nodes from body
4. Generate code: `ast.unparse(tree)`
5. Format code: `format_code_with_black()`
6. Write to file

**Comment-to-Docstring Conversion Logic**:
```python
def convert_comments_to_docstrings(tree: ast.Module) -> ast.Module:
    """
    Convert comment nodes to docstrings in AST.
    
    Comments are converted to docstrings before functions/classes.
    """
    def process_node(node: ast.AST, parent_body: List[ast.stmt]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Find comment nodes before this node
            node_idx = parent_body.index(node)
            comments_before = []
            
            # Collect comments before this node
            for i in range(node_idx - 1, -1, -1):
                prev_node = parent_body[i]
                if isinstance(prev_node, ast.Expr):
                    if isinstance(prev_node.value, ast.Constant):
                        comment_text = prev_node.value.value
                        if isinstance(comment_text, str) and comment_text.startswith("#"):
                            # Extract comment text (remove # and whitespace)
                            comment_content = comment_text[1:].strip()
                            comments_before.insert(0, comment_content)
                            # Remove comment node
                            parent_body.pop(i)
                        else:
                            break
                    else:
                        break
                else:
                    break
            
            # If comments found, add as docstring
            if comments_before and not ast.get_docstring(node):
                docstring_text = "\n".join(comments_before)
                # Add docstring as first statement in body
                docstring_node = ast.Expr(ast.Constant(value=docstring_text))
                node.body.insert(0, docstring_node)
        
        # Process children recursively
        if hasattr(node, "body") and isinstance(node.body, list):
            for child in node.body[:]:
                process_node(child, node.body)
    
    # Process all nodes
    for node in tree.body[:]:
        process_node(node, tree.body)
    
    return tree
```

#### Step 2.3: Update Documentation

**File**: `docs/AST_VS_CST_ARCHITECTURE.md`

**Tasks**:
1. Update section about AST restoration
2. Document comment preservation approach
3. Explain comment-to-docstring conversion
4. Update status section

**Changes**:
- Update: "AST restoration is now feasible with comment preservation"
- Add: "Comments are preserved in AST using `_parse_with_comments()`"
- Add: "Comments are converted to docstrings during restoration"
- Add: "Formatting is lost but can be restored with black"

#### Step 2.4: Enhance CST Restoration (Optional)

**File**: `code_analysis/commands/file_management.py`

**Enhancements** (if needed):

1. **Add validation**:
```python
# After restoring file, validate it's valid Python
try:
    ast.parse(cst_code, filename=str(target_path))
except SyntaxError as e:
    logger.error(f"Restored file has syntax errors: {e}")
    return False
```

2. **Add version selection**:
```python
async def _restore_file_from_cst(
    self, 
    file_id: int, 
    file_path: str, 
    file_record: Dict[str, Any],
    cst_hash: Optional[str] = None  # Optional: restore specific version
) -> bool:
    """
    Restore file from CST (source code stored in database).
    
    Args:
        cst_hash: Optional CST hash to restore specific version
    """
    if cst_hash:
        # Get specific CST version by hash
        cst_data = await self.database.get_cst_tree_by_hash(file_id, cst_hash)
    else:
        # Get latest CST version
        cst_data = await self.database.get_cst_tree(file_id)
    # ... rest of implementation
```

3. **Add restoration metadata**:
```python
# Log restoration details
logger.info(
    f"Restored file {file_path} from CST "
    f"(hash: {cst_data.get('cst_hash')}, "
    f"mtime: {cst_data.get('file_mtime')})"
)
```

#### Step 2.5: Add Database Method for AST Retrieval

**File**: `code_analysis/core/database/ast.py` (if exists) or `code_analysis/core/database/base.py`

**Method**:
```python
def get_ast_tree(self, file_id: int) -> Optional[Dict[str, Any]]:
    """
    Get AST tree for a file.
    
    Args:
        file_id: File ID
        
    Returns:
        AST data or None if not found:
        {
            "id": int,
            "file_id": int,
            "project_id": str,
            "ast_json": str,  # JSON-serialized AST
            "ast_hash": str,
            "file_mtime": float,
            "created_at": float,
            "updated_at": float
        }
    """
    row = self._fetchone(
        """
        SELECT id, file_id, project_id, ast_json, ast_hash, file_mtime, 
               created_at, updated_at
        FROM ast_trees
        WHERE file_id = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (file_id,),
    )
    return row
```

#### Step 2.6: Add Database Method for CST by Hash (if needed)

**File**: `code_analysis/core/database/cst.py`

**Method** (if version selection is needed):
```python
async def get_cst_tree_by_hash(
    self, file_id: int, cst_hash: str
) -> Optional[Dict[str, Any]]:
    """
    Get CST tree by specific hash.
    
    Args:
        file_id: File ID
        cst_hash: CST hash
        
    Returns:
        CST data or None if not found
    """
    row = self._fetchone(
        """
        SELECT id, file_id, project_id, cst_code, cst_hash, file_mtime, 
               created_at, updated_at
        FROM cst_trees
        WHERE file_id = ? AND cst_hash = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (file_id, cst_hash),
    )
    return row
```

#### Step 2.7: Update Repair Database to Use AST as Fallback

**File**: `code_analysis/commands/file_management.py`

**Method**: `execute()` in `RepairDatabaseCommand`

**Tasks**:
1. Try CST restoration first (current implementation)
2. If CST not available, try AST restoration
3. Log which method was used

**Logic**:
```python
# Try CST restoration first
cst_restored = await self._restore_file_from_cst(file_id, file_path, file_record)
if cst_restored:
    logger.info(f"Restored {file_path} from CST")
    continue

# Fallback to AST restoration
ast_restored = await self._restore_file_from_ast(file_id, file_path, file_record)
if ast_restored:
    logger.info(f"Restored {file_path} from AST (comments converted to docstrings)")
    continue

logger.warning(f"Could not restore {file_path} - no CST or AST available")
```

#### Step 2.8: Update TODO Comments

**File**: `code_analysis/commands/refactor.py`

**Tasks**:
1. Remove TODO comment about ClassMerger
2. Add implementation note

**Change**:
```python
# Before:
# TODO: Add ClassMerger when available
# from ..core.refactorer_pkg.merger import ClassMerger

# After:
from ..core.refactorer_pkg.merger import ClassMerger
```

**File**: `docs/AST_VS_CST_ARCHITECTURE.md`

**Tasks**:
1. Remove TODO about AST restoration
2. Document current state

### 2.5 Testing Requirements

**Tests for AST Restoration**:
1. Test AST saving with comments preserved
2. Test comment-to-docstring conversion
3. Test restoration from AST with comments
4. Test restoration when comments are present
5. Test restoration when no comments are present
6. Test validation of restored file (syntax check)
7. Test error handling (no AST found, invalid AST, etc.)
8. Test that restored file can be parsed and executed

**Tests for CST Restoration** (if enhanced):
1. Test restoration from latest CST
2. Test restoration from specific CST hash
3. Test validation of restored file
4. Test error handling (no CST found, invalid CST, etc.)

**Integration Tests**:
1. Test repair_database with CST restoration
2. Test repair_database with AST restoration (fallback)
3. Test repair_database when both CST and AST are available (prefer CST)
4. Test repair_database when neither CST nor AST is available (error)

---

## 3. Testing Strategy

### 3.1 ClassMerger Tests

**Test Cases**:
1. **Basic merge**: Merge 2 simple classes
2. **Merge with conflicts**: Merge classes with same method names
3. **Merge with properties**: Merge classes with properties
4. **Merge with docstrings**: Test docstring preservation
5. **Merge with nested classes**: Test nested class handling
6. **Error cases**: Invalid config, class not found, etc.
7. **Preview mode**: Test preview without applying changes
8. **Backup and restore**: Test backup creation and restoration on error

**Test Files**:
- `tests/test_merger.py`
- `test_data/merge_test_cases/simple_merge.py`
- `test_data/merge_test_cases/conflict_merge.py`
- `test_data/merge_test_cases/complex_merge.py`

### 3.2 File Restoration Tests

**Test Cases** (if enhanced):
1. Restore from latest CST
2. Restore from specific CST hash
3. Validate restored file syntax
4. Test error handling (no CST, invalid CST)

---

## 4. Integration Points

### 4.1 ClassMerger Integration

**Files to Modify**:
1. ✅ `code_analysis/core/refactorer_pkg/merger.py` - **NEW FILE**
2. ✅ `code_analysis/commands/refactor.py` - Add import and method
3. ✅ `code_analysis/commands/refactor_mcp_commands.py` - Add MCP command
4. ✅ `code_analysis/hooks.py` - Register command

**Dependencies**:
- `BaseRefactorer` (base class)
- `format_code_with_black` (code formatting)
- `ast` module (AST manipulation)

### 4.2 File Restoration Integration

**Files to Modify** (if enhanced):
1. `code_analysis/commands/file_management.py` - Enhance `_restore_file_from_cst()`
2. `code_analysis/core/database/cst.py` - Add `get_cst_tree_by_hash()` (if needed)
3. `docs/AST_VS_CST_ARCHITECTURE.md` - Update documentation

**Dependencies**:
- `CodeDatabase.get_cst_tree()` (already exists)
- `Path` operations (file system)

---

## 5. Implementation Priority

### Priority 1: ClassMerger (High Priority)
- **Reason**: Requested feature, inverse of existing ClassSplitter
- **Complexity**: High (requires conflict resolution, AST manipulation)
- **Estimated Time**: 2-3 days

### Priority 2: AST Restoration with Comment Preservation (Medium Priority)
- **Reason**: Enables file restoration from AST when CST is not available
- **Complexity**: Medium (requires AST manipulation, comment conversion)
- **Estimated Time**: 1-2 days
- **Key Features**:
  - Update AST saving to preserve comments
  - Implement AST restoration with comment-to-docstring conversion
  - Add fallback logic in repair_database

### Priority 3: File Restoration Documentation (Low Priority)
- **Reason**: Document both CST and AST restoration approaches
- **Complexity**: Low (documentation only)
- **Estimated Time**: 1-2 hours

### Priority 4: File Restoration Enhancements (Optional)
- **Reason**: Nice to have, not critical
- **Complexity**: Low-Medium
- **Estimated Time**: 4-6 hours

---

## 6. Success Criteria

### ClassMerger:
- ✅ Can merge 2+ classes into one
- ✅ Handles method conflicts correctly
- ✅ Handles property conflicts correctly
- ✅ Preserves docstrings
- ✅ Validates completeness
- ✅ Creates backups
- ✅ Restores backups on error
- ✅ Formats code with black
- ✅ Validates Python syntax

### File Restoration:
- ✅ AST saving preserves comments using `_parse_with_comments()`
- ✅ AST restoration converts comments to docstrings
- ✅ CST restoration works (already implemented)
- ✅ Repair database uses CST first, AST as fallback
- ✅ Documentation updated (explains both approaches)
- ✅ (Optional) Enhanced with validation and version selection

---

## 7. Notes and Considerations

### ClassMerger Considerations:
1. **Wrapper Method Detection**: Need to detect if method is a wrapper (delegates to another class instance)
2. **Property Initialization**: Need to merge `__init__` methods correctly
3. **Type Hints**: Preserve type hints from source classes
4. **Decorators**: Preserve method and class decorators
5. **Import Dependencies**: May need to add imports if merged class uses new dependencies

### File Restoration Considerations:
1. **AST with Comments**: AST can preserve comments using `_parse_with_comments()`
2. **Comment-to-Docstring**: Comments can be converted to docstrings during restoration
3. **Formatting Loss**: Formatting is lost but can be restored with black (not critical)
4. **CST Advantage**: CST preserves full source code (preferred method)
5. **Fallback Strategy**: Use CST first, AST as fallback
6. **Version Selection**: May want to restore specific version by hash
7. **Validation**: Should validate restored file is valid Python
8. **User Requirements**: Formatting not critical, comments/docstrings are critical

---

## 8. References

- `code_analysis/core/refactorer_pkg/splitter.py` - ClassSplitter implementation (reference)
- `code_analysis/core/refactorer_pkg/extractor.py` - SuperclassExtractor (reference)
- `code_analysis/core/refactorer_pkg/base.py` - BaseRefactorer (base class)
- `code_analysis/commands/file_management.py` - File restoration (current implementation)
- `code_analysis/core/database/cst.py` - CST database methods
- `docs/AST_VS_CST_ARCHITECTURE.md` - Architecture documentation

---

**End of Document**

