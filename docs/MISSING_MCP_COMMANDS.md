# Missing MCP Commands

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

## Overview

This document lists CLI commands that don't have MCP equivalents yet.

## Missing Commands

### 1. Server Management Commands

**CLI**: `code_analysis server {start|stop|status|restart}`

**Status**: ❌ Not available in MCP

**Commands needed**:
- `start_server` - Start MCP server
- `stop_server` - Stop MCP server  
- `restart_server` - Restart MCP server
- `server_status` - Get server status

**Implementation**: Use `ServerControl` class from `code_analysis.core.server_control`

### 2. Search Commands

#### 2.1 Fulltext Search

**CLI**: `code_analysis search fulltext --root-dir /path "query"`

**Status**: ❌ Not available in MCP

**Note**: MCP has `semantic_search`, but not `fulltext` search

**Command needed**: `fulltext_search`

**Implementation**: Use `SearchCommand.full_text_search()` from `code_analysis.commands.search`

#### 2.2 Class Methods

**CLI**: `code_analysis search class-methods --root-dir /path ClassName`

**Status**: ❌ Not available in MCP

**Command needed**: `list_class_methods`

**Implementation**: Use `SearchCommand.search_methods()` filtered by class_name

#### 2.3 Find Classes

**CLI**: `code_analysis search find-classes --root-dir /path "pattern"`

**Status**: ❌ Not available in MCP

**Command needed**: `find_classes`

**Implementation**: Use `SearchCommand.search_classes()` from `code_analysis.commands.search`

### 3. Code Mapper / Index Update

**CLI**: `code_mapper --root-dir /path --output-dir code_analysis --max-lines 400`

**Status**: ❌ Not available in MCP

**Note**: This is essentially `analyze_project`, but `code_mapper` is a separate utility that also generates YAML reports

**Command needed**: `update_indexes` or `run_code_mapper`

**Implementation**: Use `CodeMapper` class from `code_analysis.code_mapper`

## Priority

1. **High Priority**:
   - Server management commands (needed for server lifecycle management via MCP)
   - Fulltext search (complements semantic_search)

2. **Medium Priority**:
   - Class methods listing
   - Find classes by pattern

3. **Low Priority**:
   - Code mapper/index update (can use `analyze_project` instead)

## Implementation Plan

1. Create `code_analysis/commands/server_management_commands.py`
2. Create `code_analysis/commands/search_mcp_commands.py` (or extend existing)
3. Register all new commands in `code_analysis/hooks.py`
4. Test via MCP Proxy

