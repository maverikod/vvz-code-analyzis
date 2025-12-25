# CLI Commands Reference

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Overview

All MCP commands are available through CLI. The structure is:
- **Business logic** in `code_analysis/commands/` (internal commands)
- **MCP wrappers** in `code_analysis/commands/*_mcp_commands.py` (MCP API)
- **CLI wrappers** in `code_analysis/cli/` (CLI interface)

## Command Groups

### analyze
Analyze Python project or file.

```bash
code_analysis analyze --root-dir /path --max-lines 400
code_analysis analyze --root-dir /path --file-path file.py
```

### search
Search operations - find usages, full-text search, semantic search.

```bash
code_analysis search find-usages --root-dir /path --name method_name
code_analysis search fulltext --root-dir /path "query"
code_analysis search semantic --root-dir /path "query" --k 10
```

### refactor
Code refactoring operations.

```bash
code_analysis refactor split-class --root-dir /path --file file.py --config config.json
code_analysis refactor extract-superclass --root-dir /path --file file.py --config config.json
code_analysis refactor split-file-to-package --root-dir /path --file file.py --config config.json
```

### ast
AST operations - work with Abstract Syntax Trees.

```bash
code_analysis ast get-ast --root-dir /path --file-path file.py
code_analysis ast search-nodes --root-dir /path --node-type ClassDef
code_analysis ast statistics --root-dir /path
code_analysis ast list-files --root-dir /path
code_analysis ast get-entity-info --root-dir /path --entity-type class --entity-name ClassName
code_analysis ast list-entities --root-dir /path --entity-type class
```

### analysis
Analysis operations - dependencies, imports, hierarchy, usages.

```bash
code_analysis analysis get-imports --root-dir /path
code_analysis analysis find-dependencies --root-dir /path
code_analysis analysis class-hierarchy --root-dir /path
code_analysis analysis find-usages --root-dir /path --name method_name
code_analysis analysis export-graph --root-dir /path --output graph.dot
```

### vector
Vectorization operations - check vectors, rebuild FAISS, revectorize.

```bash
code_analysis vector check --root-dir /path
code_analysis vector rebuild-faiss --root-dir /path
code_analysis vector revectorize --root-dir /path
```

### server
Server management operations.

```bash
code_analysis server start --config config.json
code_analysis server stop
code_analysis server status
code_analysis server restart --config config.json
```

### system
System operations - help and health.

```bash
code_analysis system help
code_analysis system help --command analyze_project
code_analysis system health
code_analysis system health --server-url https://localhost:15000
```

## Command Structure

All commands follow the same pattern:

1. **Internal command** (`code_analysis/commands/`) - contains business logic
2. **MCP wrapper** (`code_analysis/commands/*_mcp_commands.py`) - MCP API interface
3. **CLI wrapper** (`code_analysis/cli/*_cli.py`) - CLI interface

Both MCP and CLI call the same internal command, ensuring consistency.

