# Missing MCP Commands

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

## Overview

This document lists CLI commands that don't have MCP equivalents yet.

## Missing Commands

### 1. Server Management Commands

**CLI**: `code_analysis server {start|stop|status|restart}`

**Status**: ⏸️ Skipped (not needed in MCP)

**Note**: Server management is handled via CLI or direct ServerControl usage. Not needed in MCP interface.

### 2. Search Commands

#### 2.1 Fulltext Search

**CLI**: `code_analysis search fulltext --root-dir /path "query"`

**Status**: ✅ **COMPLETED** - Available in MCP as `fulltext_search`

**Command**: `fulltext_search`

**Implementation**: `FulltextSearchMCPCommand` in `code_analysis/commands/search_mcp_commands.py`

#### 2.2 Class Methods

**CLI**: `code_analysis search class-methods --root-dir /path ClassName`

**Status**: ✅ **COMPLETED** - Available in MCP as `list_class_methods`

**Command**: `list_class_methods`

**Implementation**: `ListClassMethodsMCPCommand` in `code_analysis/commands/search_mcp_commands.py`

#### 2.3 Find Classes

**CLI**: `code_analysis search find-classes --root-dir /path "pattern"`

**Status**: ✅ **COMPLETED** - Available in MCP as `find_classes`

**Command**: `find_classes`

**Implementation**: `FindClassesMCPCommand` in `code_analysis/commands/search_mcp_commands.py`

### 3. Code Mapper / Index Update

**CLI**: `code_mapper --root-dir /path --output-dir code_analysis --max-lines 400`

**Status**: ✅ **COMPLETED** - Available in MCP as `update_indexes`

**Command**: `update_indexes`

**Implementation**: `UpdateIndexesMCPCommand` in `code_analysis/commands/code_mapper_mcp_command.py`

**Note**: Uses queue system for long-running operations

## Status Summary

✅ **All required commands implemented and tested**

### Completed Commands

1. ✅ `fulltext_search` - Full-text search in code content and docstrings
2. ✅ `list_class_methods` - List all methods of a class
3. ✅ `find_classes` - Find classes by name pattern
4. ✅ `update_indexes` - Update code indexes using code_mapper

### Implementation Details

1. ✅ Created `code_analysis/commands/search_mcp_commands.py` with three search commands
2. ✅ Created `code_analysis/commands/code_mapper_mcp_command.py` for index updates
3. ✅ Registered all commands in `code_analysis/hooks.py`
4. ✅ Tested via MCP Proxy - all commands working correctly

### Testing Results

All commands tested successfully via MCP Proxy:
- `fulltext_search` - ✅ Working
- `list_class_methods` - ✅ Working
- `find_classes` - ✅ Working
- `update_indexes` - ✅ Registered (uses queue system)

