# Command Architecture

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Overview

All commands follow a three-layer architecture:

1. **Business Logic Layer** (`code_analysis/commands/`) - Internal command implementations
2. **MCP API Layer** (`code_analysis/commands/*_mcp_commands.py`) - MCP Proxy wrappers
3. **CLI Layer** (`code_analysis/cli/*_cli.py`) - Command-line interface wrappers

Both MCP and CLI call the same internal commands, ensuring consistency and avoiding code duplication.

## Structure

```
code_analysis/
├── commands/              # Business logic layer
│   ├── analyze.py         # AnalyzeCommand (internal)
│   ├── search.py          # SearchCommand (internal)
│   ├── refactor.py        # RefactorCommand (internal)
│   ├── get_ast.py         # GetASTCommand (internal)
│   ├── semantic_search.py # SemanticSearchCommand (internal)
│   └── ...
│
├── commands/              # MCP API layer
│   ├── analyze_project_command.py    # AnalyzeProjectCommand (MCP wrapper)
│   ├── analyze_file_command.py      # AnalyzeFileCommand (MCP wrapper)
│   ├── ast_mcp_commands.py          # GetASTMCPCommand, etc. (MCP wrappers)
│   ├── semantic_search_mcp.py       # SemanticSearchMCPCommand (MCP wrapper)
│   └── ...
│
└── cli/                   # CLI layer
    ├── main_cli.py        # analyze command (CLI wrapper)
    ├── search_cli.py      # search commands (CLI wrappers)
    ├── refactor_cli.py    # refactor commands (CLI wrappers)
    ├── ast_cli.py         # ast commands (CLI wrappers)
    ├── analysis_cli.py    # analysis commands (CLI wrappers)
    └── vector_cli.py      # vector commands (CLI wrappers)
```

## Command Flow

### Example: Get AST

1. **Internal Command** (`GetASTCommand` in `commands/get_ast.py`)
   ```python
   class GetASTCommand:
       def __init__(self, database, project_id, file_path, ...):
           ...
       async def execute(self):
           # Business logic here
           ...
   ```

2. **MCP Wrapper** (`GetASTMCPCommand` in `commands/ast_mcp_commands.py`)
   ```python
   class GetASTMCPCommand(Command):
       async def execute(self, root_dir, file_path, ...):
           db = _open_database(root_dir)
           cmd = GetASTCommand(db, proj_id, file_path, ...)
           result = await cmd.execute()
           return SuccessResult(data=result)
   ```

3. **CLI Wrapper** (`get_ast` in `cli/ast_cli.py`)
   ```python
   @ast.command()
   def get_ast(root_dir, file_path, ...):
       db = _open_database(root_dir)
       cmd = GetASTCommand(db, proj_id, file_path, ...)
       result = asyncio.run(cmd.execute())
       click.echo(result)
   ```

## Available Commands

### MCP Commands (28 total)

All registered in `code_analysis/hooks.py`:

1. `analyze_project` - Analyze entire project
2. `analyze_file` - Analyze single file
3. `help` - Get help information
4. `check_vectors` - Check vector statistics
5. `get_ast` - Get AST for file
6. `search_ast_nodes` - Search AST nodes
7. `ast_statistics` - Get AST statistics
8. `list_project_files` - List project files
9. `get_code_entity_info` - Get entity information
10. `list_code_entities` - List code entities
11. `get_imports` - Get imports
12. `find_dependencies` - Find dependencies
13. `get_class_hierarchy` - Get class hierarchy
14. `find_usages` - Find usages
15. `export_graph` - Export graph
16. `rebuild_faiss` - Rebuild FAISS index
17. `revectorize` - Revectorize chunks
18. `semantic_search` - Semantic search
19. `add_watch_dir` - Add watch directory
20. `remove_watch_dir` - Remove watch directory
21. `split_class` - Split class
22. `extract_superclass` - Extract superclass
23. `split_file_to_package` - Split file to package

### CLI Commands

All available through `code_analysis.cli.main`:

1. `analyze` - Analyze project/file
2. `search` - Search operations
   - `find-usages` - Find usages
   - `fulltext` - Full-text search
   - `semantic` - Semantic search
   - `class-methods` - List class methods
   - `find-classes` - Find classes
3. `refactor` - Refactoring operations
   - `split-class` - Split class
   - `extract-superclass` - Extract superclass
   - `split-file-to-package` - Split file to package
4. `ast` - AST operations
   - `get-ast` - Get AST
   - `search-nodes` - Search nodes
   - `statistics` - AST statistics
   - `list-files` - List files
   - `get-entity-info` - Get entity info
   - `list-entities` - List entities
5. `analysis` - Analysis operations
   - `get-imports` - Get imports
   - `find-dependencies` - Find dependencies
   - `class-hierarchy` - Class hierarchy
   - `find-usages` - Find usages
   - `export-graph` - Export graph
6. `vector` - Vectorization operations
   - `check` - Check vectors
   - `rebuild-faiss` - Rebuild FAISS
   - `revectorize` - Revectorize
7. `server` - Server management
   - `start` - Start server
   - `stop` - Stop server
   - `status` - Get status
   - `restart` - Restart server

## Benefits

1. **Single Source of Truth** - Business logic in one place
2. **Consistency** - MCP and CLI produce same results
3. **Maintainability** - Changes in one place affect both interfaces
4. **Testability** - Internal commands can be tested independently
5. **Extensibility** - Easy to add new interfaces (REST API, etc.)

