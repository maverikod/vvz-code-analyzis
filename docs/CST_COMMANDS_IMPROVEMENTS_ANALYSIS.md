# Analysis: CST Commands Improvements Based on Real Usage

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-12

## Executive Summary

This document analyzes real-world usage of CST commands during code fixing and identifies improvements needed to make commands more optimal and user-friendly.

## Context: Attempted Code Fix

**Task**: Fix test server code in `test_data/particles/server.py`

**Issues Found**:
1. Line 143: `engine` variable undefined (critical error)
2. Line 136: `engine_factory` created but never used
3. Line 122: `app` created but never used

**Attempted Solution**: Use `cst_modify_tree` to replace problematic code with correct implementation.

## Problems Encountered

### 1. `cst_modify_tree` Replace Operation Limitations

**Problem**: Cannot replace a single `SimpleStatementLine` node with multiple statements.

**Error**: `"Invalid operation: Node stmt:main:SimpleStatementLine:143:8-143:33 was not replaced"`

**Root Cause Analysis**:
- `_replace_node` in `tree_modifier.py` has logic to handle multiple statements
- `NodeReplacer` transformer handles replacement in `leave_Module` and `leave_IndentedBlock`
- However, `leave_SimpleStatementLine` does nothing and relies on parent handlers
- If the SimpleStatementLine is deeply nested or in a complex context, replacement may fail
- The check `if not replacer.replaced: raise ValueError` fails even when code is valid

**Current Implementation** (lines 388-396):
```python
def leave_SimpleStatementLine(
    self,
    original_node: cst.SimpleStatementLine,
    updated_node: cst.SimpleStatementLine,
) -> cst.SimpleStatementLine:
    # If replacing SimpleStatementLine with multiple statements,
    # we need to replace it at the parent level (IndentedBlock/Module)
    # This is handled in leave_IndentedBlock/leave_Module
    return updated_node
```

**Issue**: The parent handlers may not always catch the replacement correctly.

### 2. `cst_modify_tree` Insert Operation Limitations

**Problem**: Cannot insert code relative to a `SimpleStatementLine` node.

**Error**: `"Invalid operation: Nodes were not inserted relative to target node stmt:main:SimpleStatementLine:134:8-134:76 in parent node:main:IndentedBlock:67:8-145:16"`

**Root Cause Analysis**:
- `_insert_node_relative` finds parent for `target_node_id`
- But insertion logic in `NodeInserter` only handles `ClassDef`, `FunctionDef`, and `Module`
- It doesn't handle inserting relative to a `SimpleStatementLine` within an `IndentedBlock`
- The transformer needs to handle insertion at statement level within blocks

**Current Implementation** (lines 419-453):
```python
def on_leave(
    self, original_node: cst.CSTNode, updated_node: cst.CSTNode
) -> cst.CSTNode:
    if original_node is self.target_parent:
        # Insert nodes into parent's body
        if isinstance(updated_node, (cst.ClassDef, cst.FunctionDef)):
            # ... handles ClassDef/FunctionDef
        elif isinstance(updated_node, cst.Module):
            # ... handles Module
        # MISSING: Handle IndentedBlock case
    return updated_node
```

### 3. `compose_cst_module` API Change

**Problem**: Command signature changed from `ops`-based to `tree_id`-based, but documentation still references old API.

**Current Schema** (requires):
- `project_id` (required)
- `file_path` (required)
- `tree_id` (required)
- `commit_message` (optional)

**Old API** (documented but not supported):
- `root_dir` (optional)
- `file_path` (required)
- `ops` (list of operations with selectors)
- `apply` (boolean)
- `create_backup` (boolean)
- `return_diff` (boolean)

**Impact**: Confusion about which API to use. Documentation shows old API, but implementation requires new API.

### 4. Tree Lifecycle Management

**Problem**: Tree IDs become invalid after `cst_save_tree`, requiring file reload.

**Workflow Issue**:
1. `cst_load_file` → returns `tree_id_1`
2. `cst_modify_tree` with `tree_id_1` → returns `tree_id_2` (new tree)
3. `cst_save_tree` with `tree_id_2` → saves file
4. Next operation needs new `tree_id` → must reload file

**Impact**: Extra `cst_load_file` calls after each save operation.

## Proposed Improvements

### 1. Fix `cst_modify_tree` Replace for SimpleStatementLine

**Improvement**: Enhance `_replace_node` to properly handle SimpleStatementLine replacement with multiple statements.

**Changes Needed**:
1. Add explicit handling in `leave_IndentedBlock` for SimpleStatementLine replacement
2. Ensure replacement works even when SimpleStatementLine is deeply nested
3. Improve error messages to indicate why replacement failed

**Code Changes**:
```python
def leave_IndentedBlock(
    self,
    original_node: cst.IndentedBlock,
    updated_node: cst.IndentedBlock,
) -> cst.IndentedBlock:
    # Handle block-level replacements (including multiple statements)
    if any(stmt is self.target_node for stmt in original_node.body):
        new_body: list[cst.BaseStatement] = []
        for stmt in original_node.body:
            if stmt is self.target_node:
                new_body.extend(self.replacements)
                self.replaced = True
            else:
                new_body.append(stmt)
        if self.replaced:
            return updated_node.with_changes(body=new_body)
    return updated_node
```

**Note**: This logic exists but may not work correctly for all cases. Need to add debugging/logging to understand why replacement fails.

### 2. Fix `cst_modify_tree` Insert for Statement-Level Insertion

**Improvement**: Add support for inserting relative to statements within IndentedBlock.

**Changes Needed**:
1. Add `leave_IndentedBlock` handler in `NodeInserter`
2. Support insertion before/after specific statements within a block
3. Handle both `target_node_id` (insert relative to node) and `parent_node_id` (insert at block start/end)

**Code Changes**:
```python
def leave_IndentedBlock(
    self,
    original_node: cst.IndentedBlock,
    updated_node: cst.IndentedBlock,
) -> cst.IndentedBlock:
    # Handle insertion relative to statements within block
    if self.target_node_id:
        # Find target statement in block
        target_idx = None
        for idx, stmt in enumerate(original_node.body):
            if self._is_target_node(stmt, self.target_node_id):
                target_idx = idx
                break
        
        if target_idx is not None:
            new_body = list(updated_node.body)
            if self.position == "before":
                new_body[target_idx:target_idx] = self.new_statements
            else:  # after
                new_body[target_idx + 1:target_idx + 1] = self.new_statements
            self.inserted = True
            return updated_node.with_changes(body=new_body)
    
    return updated_node
```

### 3. Add Range-Based Replace Operation

**Improvement**: Add `replace_range` operation to `cst_modify_tree` for replacing multiple consecutive nodes.

**New Operation Type**:
```python
{
    "action": "replace_range",
    "start_node_id": "stmt:main:SimpleStatementLine:134:8-134:76",
    "end_node_id": "stmt:main:SimpleStatementLine:143:8-143:33",
    "code_lines": [
        "        # Run server",
        "        from mcp_proxy_adapter.core.server_engine import ServerEngineFactory",
        "",
        "        engine = ServerEngineFactory.get_engine(\"hypercorn\")",
        "        if not engine:",
        "            print(\"❌ Hypercorn engine not available\", file=sys.stderr)",
        "            sys.exit(1)",
        "",
        "        # Prepare server configuration",
        "        server_config = {",
        "            \"host\": config.model.server.host,",
        "            \"port\": config.model.server.port,",
        "            \"log_level\": \"info\",",
        "            \"reload\": False,",
        "        }",
        "",
        "        engine.run_server(app, server_config)"
    ]
}
```

**Benefits**:
- More intuitive for replacing code blocks
- Handles multiple consecutive statements
- Works better than trying to replace single nodes

### 4. Restore `compose_cst_module` with `ops` Parameter

**Improvement**: Support both old API (`ops`-based) and new API (`tree_id`-based).

**Hybrid Approach**:
- If `tree_id` provided → use tree-based approach (current)
- If `ops` provided → use ops-based approach (legacy, but more convenient for some use cases)
- Support both in same command

**Schema**:
```python
{
    "type": "object",
    "properties": {
        "project_id": {"type": "string"},
        "file_path": {"type": "string"},
        "tree_id": {"type": "string"},  # New API
        "ops": {  # Old API
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "selector": {...},
                    "new_code": {"type": "string"},
                    "code_lines": {"type": "array"}
                }
            }
        },
        "root_dir": {"type": "string"},  # For ops-based API
        "apply": {"type": "boolean"},
        "create_backup": {"type": "boolean"},
        "return_diff": {"type": "boolean"},
        "commit_message": {"type": "string"}
    },
    "anyOf": [
        {"required": ["project_id", "file_path", "tree_id"]},
        {"required": ["root_dir", "file_path", "ops"]}
    ]
}
```

### 5. Improve Tree Lifecycle Management

**Improvement**: Keep tree valid after save, or provide `cst_reload_tree` command.

**Option A**: Keep tree valid after save
- Don't invalidate tree after `cst_save_tree`
- Update tree in-place after save
- Return same `tree_id` (or indicate tree is still valid)

**Option B**: Add `cst_reload_tree` command
- Reload file into existing tree_id
- Update tree with latest file content
- Useful for refreshing tree after external changes

**Option C**: Add `cst_get_tree_status` command
- Check if tree is still valid
- Get tree metadata (file_path, last_modified, etc.)
- Helpful for debugging

### 6. Better Error Messages

**Improvement**: Provide more detailed error messages explaining why operations fail.

**Current**: `"Invalid operation: Node stmt:main:SimpleStatementLine:143:8-143:33 was not replaced"`

**Improved**:
```json
{
    "error": "INVALID_OPERATION",
    "message": "Node replacement failed",
    "details": {
        "node_id": "stmt:main:SimpleStatementLine:143:8-143:33",
        "node_type": "SimpleStatementLine",
        "reason": "Replacement code contains multiple statements, but node is not in a replaceable context (Module or IndentedBlock body)",
        "suggestion": "Try using replace_range operation or replace parent IndentedBlock",
        "node_context": {
            "parent_type": "IndentedBlock",
            "parent_id": "node:main:IndentedBlock:67:8-145:16",
            "sibling_count": 18
        }
    }
}
```

### 7. Add Operation Preview

**Improvement**: Add `preview` parameter to `cst_modify_tree` to see changes before applying.

**Usage**:
```python
{
    "tree_id": "...",
    "operations": [...],
    "preview": true  # Don't apply, just return what would change
}
```

**Response**:
```json
{
    "success": true,
    "preview": true,
    "changes": [
        {
            "operation": "replace",
            "node_id": "...",
            "old_code": "asyncio.run(engine.run())",
            "new_code": "engine = ServerEngineFactory.get_engine(\"hypercorn\")\n..."
        }
    ],
    "validation": {
        "syntax_valid": true,
        "compiles": true
    }
}
```

## Priority Recommendations

### High Priority (Critical for Usability)

1. **Fix SimpleStatementLine replacement** - Blocks common use case
2. **Add range-based replace operation** - More intuitive for code blocks
3. **Improve error messages** - Helps users understand failures

### Medium Priority (Improves Workflow)

4. **Fix statement-level insertion** - Enables more flexible code editing
5. **Restore compose_cst_module with ops** - Better API for some use cases
6. **Add operation preview** - Helps users verify changes before applying

### Low Priority (Nice to Have)

7. **Improve tree lifecycle** - Reduces reload calls but not critical

## Implementation Notes

### Testing Strategy

1. **Unit Tests**: Test each operation type with various node types
2. **Integration Tests**: Test full workflow (load → modify → save)
3. **Edge Cases**: Test deeply nested nodes, complex contexts
4. **Error Cases**: Test invalid operations, missing nodes, syntax errors

### Backward Compatibility

- Keep existing API working
- Add new features as optional parameters
- Document migration path from old to new API

## Conclusion

The main issues encountered were:
1. **Replace operation limitations** - Cannot replace SimpleStatementLine with multiple statements reliably
2. **Insert operation limitations** - Cannot insert relative to statements within blocks
3. **API confusion** - Documentation doesn't match implementation
4. **Error messages** - Not helpful for debugging

Recommended improvements focus on:
- Fixing core operation limitations
- Adding more intuitive operations (range-based)
- Improving error reporting
- Better API consistency

These improvements would make CST commands more reliable and easier to use for real-world code editing tasks.
