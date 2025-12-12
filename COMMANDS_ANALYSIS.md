# Commands Analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Current Commands Structure

### CLI Commands

1. **analyze** (main_cli.py)
   - `code_analysis analyze --root-dir /path --output-dir /path --max-lines 400`
   - Uses: CodeMapper

2. **search** group (search_cli.py)
   - `find-usages` - Find usages of method/property
   - `fulltext` - Full-text search
   - `class-methods` - List class methods
   - `find-classes` - Find classes by pattern
   - Uses: CodeDatabase

3. **refactor** group (refactor_cli.py)
   - `split-class` - Split class into multiple
   - `extract-superclass` - Extract base class
   - `merge-classes` - Merge classes
   - Uses: ClassSplitter, SuperclassExtractor, ClassMerger

### MCP Commands (mcp_server.py)

1. `analyze_project` - Analyze project
2. `find_usages` - Find usages
3. `full_text_search` - Full-text search
4. `search_classes` - Search classes
5. `search_methods` - Search methods
6. `get_issues` - Get issues
7. `split_class` - Split class
8. `extract_superclass` - Extract superclass
9. `merge_classes` - Merge classes

## Issues

1. **Code Duplication**: Same logic in CLI and MCP
2. **No Separation**: Business logic mixed with interface
3. **Database Schema**: Uses INTEGER for project_id, should be UUID4
4. **Project Isolation**: Not all commands properly filter by project

## Solution

### 1. Create Commands Layer (`code_analysis/commands/`)

Structure:
```
commands/
├── __init__.py
├── analyze.py      # analyze_project command
├── search.py        # search commands
├── refactor.py      # refactoring commands
└── issues.py        # issues commands
```

### 2. Update Database Schema

- Change `projects.id` from INTEGER to TEXT (UUID4)
- Add `comment` field to projects table
- Ensure all tables have `project_id` with proper foreign keys

### 3. Refactor Interfaces

- CLI: Use commands layer
- MCP: Use commands layer
- API: Use commands layer

### 4. Project Isolation

- All commands must accept project_id or root_path
- All database queries must filter by project_id
- Commands return project-scoped results

