# AI Tool Usage Rules

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Overview

This document defines rules for AI models on how to use the code analysis and refactoring tools in this project. These rules ensure efficient, safe, and correct usage of the available tools.

**CRITICAL PRINCIPLE**: Code is written through **CST (Concrete Syntax Tree) operations**, not as raw text. This ensures:
- ✅ Syntax validation before applying changes
- ✅ Preservation of formatting and structure
- ✅ Atomic operations with rollback on errors
- ✅ Database consistency
- ✅ No JSON escaping issues with multi-line code

**Key Technology**: Use `code_lines` (array of strings) instead of `code` (single string) for multi-line code to avoid JSON escaping issues.

**Command parameters (source of truth)**: Most project-scoped commands use **`project_id`** (UUID from `list_projects` or from the `projectid` file in the project root). Do not rely on `root_dir` unless the command schema explicitly accepts it. Authoritative parameter list: `get_schema()` in code and [COMMANDS_GUIDE.md](COMMANDS_GUIDE.md), [COMMANDS_INDEX.md](COMMANDS_INDEX.md).

**Project-specific rules**: For this repository, rules that apply only to code under `test_data/` are in [TEST_DATA_AI_RULES.md](TEST_DATA_AI_RULES.md). The present document defines general (production) rules.

**Note on examples**: In the examples below, use **project_id** for project-scoped commands when the schema requires it; some snippets may still show `root_dir` for brevity—always check [COMMANDS_GUIDE.md](COMMANDS_GUIDE.md) or command `get_schema` for current parameters.

**Workflow and fallbacks**: For which command to use per task and what to try when a command fails, see [CST_WORKFLOW_GUIDE.md](CST_WORKFLOW_GUIDE.md) and the [CST Error Fallback Table](#73-cst-error-fallback-table) below.

## 0. AI Prompt Rules (MANDATORY)

**⚠️ CRITICAL: These rules apply ONLY when server `code-analysis-server` is available via MCP Proxy. When server is unavailable, use fallback tools with user approval.**

### 0.0 Quick Reference (For Prompt Insertion)

**⚠️ CRITICAL: These are HARD RULES when server `code-analysis-server` is available via MCP Proxy.**

**IF server is available:**

1. **Python code operations → SERVER TOOLS ONLY (MANDATORY)**
   - ✅ Editing existing Python code → `compose_cst_module` OR `cst_load_file` → `cst_modify_tree` → `cst_save_tree` (via MCP)
   - ✅ **For multi-line code**: Use `code_lines` (array of strings) in `cst_modify_tree` - avoids JSON escaping issues
   - ✅ **For test projects**: ONLY server tools, NEVER direct file editing
   - ✅ Splitting files → `split_file_to_package` (via MCP)
   - ✅ Code analysis → `comprehensive_analysis`, `get_code_entity_info` (via MCP)
   - ✅ Code quality → `format_code`, `lint_code`, `type_check_code` (via MCP)
   - ❌ **FORBIDDEN**: `search_replace` or `write` on existing `.py` files
   - ❌ **FORBIDDEN**: Direct file editing for test project code

2. **Error handling → USER DECISION REQUIRED**
   - ✅ Report ALL errors to user immediately
   - ✅ Wait for user approval before using fallback
   - ❌ **FORBIDDEN**: Silent fallback to direct file editing

3. **Why server tools are MANDATORY:**
   - Reliability: 9/10 vs 4/10 (automatic validation, backups, error handling)
   - Safety: 9/10 vs 4/10 (syntax/docstring/type validation)
   - Convenience (complex): 8/10 vs 3/10 (semantic operations)

4. **Direct tools allowed ONLY for:**
   - ✅ Creating NEW files (file doesn't exist)
   - ✅ Non-Python files (`.md`, `.json`, `.yaml`, `.txt`)
   - ✅ When server unavailable (with user notification)
   - ✅ When server fails AND user explicitly approves fallback

**Workflow for existing Python code (when server available):**

**Traditional (single operation):** Use `project_id` (required by schema).
1. `list_cst_blocks` (project_id, file_path) → discover structure
2. `compose_cst_module` with `apply=false` → preview
3. `compose_cst_module` with `apply=true` → apply
4. `comprehensive_analysis` (project_id) → validate quality

**Tree-based (multiple operations):** Use `project_id` for load/save.
1. `cst_load_file` (project_id, file_path) → load file into tree (get tree_id)
2. `cst_find_node` → find nodes to modify (simple or XPath search)
   - OR `cst_get_node_by_range` → get node_id by line range (when you know line numbers)
3. `cst_get_node_info` (optional) → inspect node details
4. `cst_modify_tree` → apply multiple operations atomically
   - Use `code_lines` (array) for multi-line code (RECOMMENDED)
   - Use `code` (string) only for single-line code
5. `cst_save_tree` (tree_id, project_id, file_path) → atomically save with backup and validation
6. `comprehensive_analysis` (project_id) → validate quality

**Remember**: Server tools = 9/10 reliability. Direct tools = 4/10 reliability. When server is available, using direct tools for Python code is a violation.

### 0.1 Core Principle

**Use server tools in specified cases WHEN server is available. If server tools fail, MANDATORY to notify user and get approval before using fallback.**

**Key Points:**
- ✅ Use server tools when available (reliability 9/10 vs 4/10)
- ✅ Report ALL errors to user immediately
- ✅ Wait for user decision before using fallback tools
- ❌ Never silently switch to direct file editing
- ❌ Never proceed without user approval on errors

### 0.2 Tool Selection Rules (MANDATORY WHEN SERVER AVAILABLE)

**IF server `code-analysis-server` is available via MCP Proxy:**

1. **MUST use server tools** for ALL Python code operations:
   - ✅ Editing existing Python code → `compose_cst_module` (MANDATORY)
   - ✅ Splitting files → `split_file_to_package` (MANDATORY)
   - ✅ Code analysis → `comprehensive_analysis`, `get_code_entity_info` (MANDATORY)
   - ✅ Code quality → `format_code`, `lint_code`, `type_check_code` (MANDATORY)

2. **NEVER use direct file editing** (`search_replace`, `write`) for existing Python code:
   - ❌ `search_replace` on existing `.py` files = FORBIDDEN
   - ❌ Direct `write` on existing `.py` files = FORBIDDEN
   - ✅ Exception: Creating NEW files from scratch only

3. **Why server tools are MANDATORY (when available):**
   - **Reliability**: 9/10 vs 4/10 (automatic validation, backups, error handling)
   - **Safety**: Syntax validation, docstring checks, type hint validation
   - **Consistency**: Preserves formatting, comments, structure
   - **Recovery**: Automatic backups before changes

### 0.3 Error Handling and Fallback Rules (MANDATORY)

**CRITICAL: When server tools fail or return errors:**

1. **MUST immediately notify user** about the error:
   - Report the exact error message from server
   - Report which command failed
   - Report what operation was attempted

2. **MUST NOT automatically switch to fallback tools**:
   - ❌ Do NOT silently use `search_replace` if `compose_cst_module` fails
   - ❌ Do NOT proceed with direct file editing without user approval
   - ✅ Wait for user decision

3. **User makes the decision**:
   - User decides whether to:
     - Retry the server command
     - Use fallback tools (direct file editing)
     - Cancel the operation
     - Investigate the error further

4. **Example error handling workflow**:
   ```
   Server tool fails → Report error to user → Wait for user decision → 
   User approves fallback → Use direct tools (with warning about reduced safety)
   ```

**Remember**: Model's role is to report errors and wait for user decision. User controls fallback strategy.

### 0.4 Code Editing Workflow (MANDATORY WHEN SERVER AVAILABLE)

**For existing Python files, ALWAYS follow this sequence (when server is available):**

1. **Discover** → `list_cst_blocks` to find code structure
2. **Preview** → `compose_cst_module` with `apply=false` to see changes
3. **Apply** → `compose_cst_module` with `apply=true` and `create_backup=true`
4. **Validate** → `format_code`, `lint_code`, `type_check_code`
5. **Analyze** → `comprehensive_analysis` after logically completed steps

**If any step fails:**
- Report error to user immediately
- Wait for user decision before proceeding
- Do NOT automatically switch to direct file editing

**NEVER skip steps 1-2. NEVER use `search_replace` for Python code (when server is available).**

### 0.5 When Direct Tools Are Allowed (EXCEPTIONS ONLY)

**Direct tools (`write`, `search_replace`) ONLY for:**
- ✅ Creating NEW files (file doesn't exist)
- ✅ Editing non-Python files (`.md`, `.json`, `.yaml`, `.txt`)
- ✅ Simple text replacements in comments/docstrings (CST still preferred)
- ✅ **When server is unavailable** (with user notification)
- ✅ **When server tool fails and user explicitly approves fallback**

**Direct tools FORBIDDEN for:**
- ❌ Modifying existing Python code (when server is available)
- ❌ Splitting large files (when server is available)
- ❌ Refactoring operations (when server is available)
- ❌ **Silent fallback without user approval**

### 0.6 Tool Comparison Summary

| Operation | Server Tools | Direct Tools | Winner |
|-----------|-------------|--------------|--------|
| **Reliability** | 9/10 (auto-validation, backups) | 4/10 (no validation) | **Server** |
| **Safety** | 9/10 (syntax/docstring checks) | 4/10 (no checks) | **Server** |
| **Convenience (complex)** | 8/10 (semantic operations) | 3/10 (manual work) | **Server** |
| **Convenience (simple)** | 5/10 (overhead) | 9/10 (direct) | Direct* |

*Direct tools only for simple non-code tasks or new files.

### 0.7 Quick Decision Tree

```
Is server available?
├─ YES → Is it Python code?
│   ├─ YES → Is file existing?
│   │   ├─ YES → Use compose_cst_module (MANDATORY)
│   │   │   └─ If fails → Report error to user → Wait for decision
│   │   └─ NO → Use write (allowed for new files)
│   └─ NO → Use write/search_replace (allowed for non-Python)
└─ NO → Notify user → Get approval → Use direct tools if approved
```

**Remember**: 
- Server tools provide 9/10 reliability vs 4/10 for direct tools
- When server is available, using direct tools for Python code is a violation
- **When server tools fail, MANDATORY to report to user and wait for decision**
- User controls fallback strategy, not the model

## 1. Tool Priority Rules

### 1.1 Primary Interface: MCP (Multi-Command Protocol)

**CRITICAL**: Always use MCP commands as the primary interface. CLI is only a fallback when MCP is unavailable.

**Priority Order**:
1. ✅ **MCP Commands** (via `mcp_MCP-Proxy-2_call_server`) - PRIMARY
2. ⚠️ **CLI** (via `run_terminal_cmd`) - FALLBACK ONLY

**Rationale**:
- MCP provides structured, validated input/output
- MCP commands are tested and maintained
- CLI is for human users, not AI automation

**Example**:
```python
# ✅ CORRECT: Use MCP
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="analyze_file",
    params={"root_dir": "/path", "file_path": "file.py"}
)

# ❌ WRONG: Using CLI directly
run_terminal_cmd("code_analysis analyze --file-path file.py")
```

### 1.2 Server Management

**Rule**: Server management (start/stop/restart) should be done via CLI, not MCP.

**When to restart server**:
- After any code changes in `code_analysis/` package
- After adding new MCP commands
- After modifying command implementations
- When server errors occur

**Command**:
```bash
cd /home/vasilyvz/projects/tools/code_analysis && \
source .venv/bin/activate && \
python -m code_analysis.cli.server_manager_cli --config config.json restart
```

## 2. Code Editing Priority Rules

**CRITICAL**: For editing existing code, **ALWAYS** use CST tools first. Direct file editing (`search_replace`, `write`) is **ONLY** for new files or when CST is not applicable.

### 2.1 Priority Order for Code Editing

**When editing existing code, use this priority (when server is available):**

1. ✅ **CST Tools** (via `compose_cst_module` MCP command) - **PRIMARY FOR EXISTING CODE**
2. ⚠️ **Direct file editing** (`search_replace`, `write`) - **ONLY FOR NEW FILES OR WHEN CST FAILS AND USER APPROVES**

**IMPORTANT**: If CST tools fail, you MUST:
- Report the error to user immediately
- Wait for user decision before using fallback tools
- Do NOT automatically switch to direct file editing

**Rationale**:
- CST preserves formatting, comments, and code structure
- CST validates syntax automatically (compile check)
- CST validates docstrings and type hints
- CST normalizes imports automatically
- Direct editing can break formatting and lose comments

### 2.2 When to Use CST Tools (PRIORITY)

**ALWAYS use CST for**:
- ✅ **Modifying existing code** (functions, classes, methods)
- ✅ **Replacing code blocks** in existing files
- ✅ **Removing code** from existing files
- ✅ **Refactoring operations**
- ✅ **When preserving comments/formatting is critical**
- ✅ **Any change to existing `.py` files**

**Two CST Approaches**:

**1. Traditional File-based CST (simpler for single operations)**:
1. **Discover**: Use `list_cst_blocks` to find blocks with stable IDs
2. **Query** (optional): Use `query_cst` for complex selectors
3. **Preview**: Use `compose_cst_module` with `apply=false` and `return_diff=true`
4. **Apply**: Use `compose_cst_module` with `apply=true` and `create_backup=true`

**2. In-Memory Tree-based CST (better for multiple operations)** - **RECOMMENDED**:
1. **Load**: Use `cst_load_file` to load file into tree (returns tree_id)
2. **Explore**: Use `cst_find_node` to find nodes (simple or XPath search)
   - OR `cst_get_node_by_range` to get node_id by line range (when you know line numbers)
3. **Inspect**: Use `cst_get_node_info` to get node details (code, children, parent)
4. **Modify**: Use `cst_modify_tree` to apply multiple operations atomically
   - **CRITICAL**: Use `code_lines` (array of strings) for multi-line code
   - Each line is a separate array element - no JSON escaping issues
   - Preserves exact formatting (indentation, empty lines)
5. **Save**: Use `cst_save_tree` to atomically save all changes with backup

**Technology Note**: CST operations work with **tree nodes**, not raw text. Code is parsed into CST nodes, modified as tree structure, then serialized back to text. This ensures:
- Syntax validation before applying
- Structure preservation
- Atomic operations
- No formatting loss

**When to use Tree-based approach**:
- ✅ Multiple related operations on the same file
- ✅ Complex refactoring requiring exploration before changes
- ✅ When you need atomicity across multiple modifications
- ✅ When you want to validate all changes together before saving

**Example - Replacing existing method**:
```python
# ✅ CORRECT: Use CST via MCP
# Step 1: List blocks to find the method
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="list_cst_blocks",
    params={"root_dir": "/path", "file_path": "file.py"}
)

# Step 2: Replace method using block_id or selector
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "ops": [{
            "selector": {"kind": "method", "name": "MyClass.old_method"},
            "new_code": "def old_method(self, param: int) -> str:\n    \"\"\"Method description.\"\"\"\n    return str(param)"
        }],
        "apply": True,
        "create_backup": True,
        "return_diff": True
    }
)
```

**Example - Removing code**:
```python
# ✅ CORRECT: Use CST to remove (empty new_code)
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "ops": [{
            "selector": {"kind": "function", "name": "unused_function"},
            "new_code": ""  # Empty string = delete
        }],
        "apply": True
    }
)
```

### 2.3 When to Write Code Directly (EXCEPTIONS ONLY)

**Use direct code writing (`write` tool) ONLY for**:
- ✅ Creating **new files/modules from scratch** (file doesn't exist)
- ✅ Creating **documentation files** (.md files)
- ✅ Creating **configuration files** (JSON, YAML, etc.)
- ✅ Creating **test files** (when file doesn't exist)

**Use `search_replace` ONLY when**:
- ⚠️ CST tools failed and you need a workaround
- ⚠️ Editing non-Python files (markdown, config, etc.)
- ⚠️ Simple text replacements in comments/docstrings (though CST is still preferred)

**Example - Creating new file**:
```python
# ✅ CORRECT: Direct write for new file
write(
    file_path="new_module.py",
    contents="\"\"\"New module.\"\"\"\n\nclass NewClass:\n    pass"
)
```

**Example - Editing existing file (WRONG)**:
```python
# ❌ WRONG: Using search_replace for existing code
search_replace(
    file_path="existing_file.py",
    old_string="def old_method(self):",
    new_string="def new_method(self, param: int) -> str:"
)
# Should use compose_cst_module instead!
```

### 2.4 Hybrid Approach

**Best Practice**: Use hybrid approach based on context:
1. **New Python files** → Direct write (`write` tool)
2. **Existing Python files** → **CST tools** (`compose_cst_module` via MCP)
3. **Complex refactoring** → Specialized commands (`split_class`, `split_file_to_package`)
4. **Non-Python files** → Direct editing (`write`, `search_replace`)

### 2.4 File Splitting Rules

**CRITICAL**: When splitting large files, **ALWAYS** use MCP proxy and splitting tools.

**Rule**: 
- ✅ **MUST** use MCP commands (`split_file_to_package`, `split_class`) via `mcp_MCP-Proxy-2_call_server`
- ❌ **NEVER** manually split files by creating new files directly
- ✅ This allows parallel testing of the code during refactoring

**Rationale**:
- MCP splitting tools preserve code structure and relationships
- Automatic testing during refactoring process
- Better code quality and consistency
- Maintains imports and dependencies correctly

**Example**:
```python
# ✅ CORRECT: Use MCP splitting command
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="split_file_to_package",
    params={
        "root_dir": "/path",
        "file_path": "large_file.py",
        "config_path": "data/refactor_configs/split_config.json"
    }
)

# ❌ WRONG: Manual file splitting
write("new_file.py", "...")  # Don't do this for splitting!
```

## 3. Code Validation Rules

### 3.1 Automatic Validation

**Rule**: `compose_cst_module` automatically validates:
- ✅ Syntax (compilation check)
- ✅ Docstrings (file, class, method)
- ✅ Type hints (parameters, return types)
- ✅ Parameter documentation in docstrings
- ✅ Attribute documentation in class docstrings

**Action**: No manual validation needed - it's automatic.

### 3.2 Manual Code Quality Checks

**When to use**:
- Before committing code
- After major refactoring
- When debugging issues

**Commands**:
```python
# Format code
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="format_code",
    params={"file_path": "file.py"}
)

# Lint code
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="lint_code",
    params={"file_path": "file.py"}
)

# Type check
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="type_check_code",
    params={"file_path": "file.py"}
)
```

## 4. File Organization Rules

### 4.1 Directory Structure

**CRITICAL**: Follow project file organization standards:

- 📁 `docs/` - ALL documentation (.md files)
- 📁 `scripts/` - Utility scripts (NOT pytest tests)
- 📁 `logs/` - Server logs
- 📁 `data/` - Database files, data files
- 📁 `tests/` - Pytest tests only
- 📁 `code_analysis/` - Source code only

**Rule**: When creating files, place them in the correct directory immediately.

### 4.2 File Size Limits

**Rule**: Files must not exceed 400 lines.

**Action**: If a file exceeds 400 lines:
1. **MUST** use MCP splitting tools (`split_file_to_package`, `split_class`)
2. Split into package structure via MCP commands
3. **NEVER** manually split by creating new files directly

**Why MCP splitting?**
- Allows parallel testing during refactoring
- Preserves code structure and relationships
- Maintains imports and dependencies correctly

**Check**:
```bash
wc -l code_analysis/**/*.py
```

**Split via MCP**:
```python
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="split_file_to_package",
    params={
        "root_dir": "/path",
        "file_path": "large_file.py",
        "config_path": "data/refactor_configs/split_config.json"
    }
)
```

## 5. Code Analysis Workflow

### 5.1 Before Making Changes

**Always**:
1. ✅ Check if functionality already exists using `code_mapper` indexes
2. ✅ Search existing code using `fulltext_search` or `semantic_search`
3. ✅ Check file size with `wc -l`
4. ✅ Review related code using `get_code_entity_info`

**Commands**:
```python
# Search for existing functionality (project_id required)
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="fulltext_search",
    params={"project_id": "<project-uuid>", "query": "functionality_name"}
)

# Get entity information
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="get_code_entity_info",
    params={"project_id": "<project-uuid>", "entity_type": "class", "entity_name": "ClassName"}
)
```

### 5.2 After Making Changes

**Always**:
1. ✅ Run `black` (automatic via `format_code`)
2. ✅ Run `flake8` (automatic via `lint_code`)
3. ✅ Run `mypy` (automatic via `type_check_code`)
4. ✅ **Run comprehensive analysis** (after each logically completed step)
5. ✅ Restart server if code changed

**Indexes**: Saving via `cst_save_tree` or `compose_cst_module` updates the database (and indexes for that file) automatically via `update_file_data_atomic`. Run `update_indexes` only when needed (e.g. initial project setup or after external file changes left indexes out of sync).

### 5.3 Comprehensive Code Quality Check

**CRITICAL**: After each logically completed step, run comprehensive analysis to check code quality.

**Rule**: 
- ✅ **MUST** run `comprehensive_analysis` after each logically completed step
- ✅ This ensures all code quality issues are detected early
- ✅ Helps maintain code quality throughout development

**When to run**:
- After implementing a new feature
- After refactoring code
- After fixing bugs
- Before committing changes
- After merging code from different branches

**Command**:
```python
# Comprehensive analysis for specific file (use project_id from list_projects)
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="comprehensive_analysis",
    params={
        "project_id": "<project-uuid>",
        "file_path": "code_analysis/core/new_module.py",  # Optional: relative to project root
        "check_placeholders": True,      # Check for TODO, FIXME, etc.
        "check_stubs": True,             # Check for pass, ellipsis, NotImplementedError
        "check_empty_methods": True,     # Check for empty methods (excluding abstract)
        "check_imports": True,           # Check imports not at top
        "check_long_files": True,        # Check files > 400 lines
        "check_duplicates": True,        # Check for code duplicates
        "check_flake8": True,            # Run flake8 linting
        "check_mypy": True,              # Run mypy type checking
        "duplicate_min_lines": 5,        # Minimum lines for duplicates
        "duplicate_min_similarity": 0.8, # Minimum similarity for duplicates
        "max_lines": 400                 # Maximum lines threshold
    },
    use_queue=True  # This is a long-running command
)

# Comprehensive analysis for entire project (use project_id from list_projects or projectid file)
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="comprehensive_analysis",
    params={
        "project_id": "<project-uuid>",
        # file_path omitted = analyze all files in project
        "check_placeholders": True,
        "check_stubs": True,
        "check_empty_methods": True,
        "check_imports": True,
        "check_long_files": True,
        "check_duplicates": True,
        "check_flake8": True,
        "check_mypy": True
    },
    use_queue=True
)

# Check job status and get results
result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="queue_get_job_status",
    params={"job_id": "comprehensive_analysis_..."}  # Job ID from previous call
)

# Results structure:
# {
#   "placeholders": [...],      # TODO, FIXME, etc.
#   "stubs": [...],            # Functions with pass, ellipsis, etc.
#   "empty_methods": [...],     # Methods without body (excluding abstract)
#   "imports_not_at_top": [...], # Imports after non-import statements
#   "long_files": [...],        # Files exceeding line limit
#   "duplicates": [...],         # Code duplicates
#   "flake8_errors": [...],      # Flake8 linting errors
#   "mypy_errors": [...],       # Mypy type checking errors
#   "summary": {
#     "total_placeholders": int,
#     "total_stubs": int,
#     "total_empty_methods": int,
#     "total_imports_not_at_top": int,
#     "total_long_files": int,
#     "total_duplicate_groups": int,
#     "total_duplicate_occurrences": int,
#     "total_flake8_errors": int,
#     "files_with_flake8_errors": int,
#     "total_mypy_errors": int,
#     "files_with_mypy_errors": int
#   }
# }
```

**Action after comprehensive analysis**:
1. ✅ Review all detected issues
2. ✅ Fix critical issues immediately (errors, duplicates, long files)
3. ✅ Address warnings and suggestions
4. ✅ Re-run analysis to verify fixes
5. ✅ Commit only after all issues are resolved

## 6. Available MCP Commands

### 6.1 Analysis Commands

- `analyze_project` - Analyze entire project
- `analyze_file` - Analyze single file
- `get_code_entity_info` - Get detailed entity information
- `list_code_entities` - List entities by type

### 6.2 Search Commands

- `fulltext_search` - Full-text search in code
- `semantic_search` - Semantic search using embeddings
- `find_classes` - Find classes by pattern
- `list_class_methods` - List methods of a class
- `find_usages` - Find usages of entity

### 6.3 AST Commands

- `get_ast` - Get AST for file
- `search_ast_nodes` - Search AST nodes
- `ast_statistics` - Get AST statistics
- `list_project_files` - List `.py` files on disk, merge DB rows when indexed; skip `.venv`/`venv` by default (`show_venv` for allowlisted venv paths only)

### 6.4 Refactoring Commands

- `file_structure` - List classes and first-level methods with line counts (use before split/extract to see sizes)
- `split_class` - Split class into multiple classes
- `extract_superclass` - Extract base class
- `split_file_to_package` - Split file into package
- `compose_cst_module` - Apply CST-based patches

### 6.5 CST Commands

**Traditional CST Commands (File-based)**:
- `list_cst_blocks` - List logical blocks with stable IDs
- `query_cst` - Query using CSTQuery selectors
- `compose_cst_module` - Apply CST patches to files directly

**`query_cst` behavior contract (IMPORTANT):**
- Query-only mode requires `selector`.
- Replace mode requires either:
  - `selector`, or
  - both `start_line` and `end_line` (range-based replace).
- If both selector and range are provided in replace mode, **range takes precedence** for replacement.
- `preview=true` or `dry_run=true` performs replace in memory and returns `diff` / `modified_source`:
  - no file write,
  - no backup creation,
  - no index/database update write path.
- `start_line` / `end_line` are 1-based and must be within file bounds with `start_line <= end_line`.

**CST Tree Commands (In-Memory Tree-based)** - **NEW**:
- `cst_load_file` - Load Python file into in-memory CST tree (returns tree_id). When the file had syntax errors on load, the response includes `syntax_errors_fixed: true`, `commented_lines` (each with `line`, `error`, `parent_node` including `node_id`), and optionally `temp_file`.
- `cst_find_node` - Find nodes in loaded tree (simple or XPath search)
- `cst_get_node_by_range` - Get node_id for a specific line range (useful when you know line numbers)
- `cst_get_node_info` - Get detailed information about a node (with code, children, parent)
- `cst_modify_tree` - Atomically modify tree in memory (replace, insert, delete operations)
- `cst_save_tree` - Atomically save modified tree to file (with backup, validation, DB update)

**When to use Tree Commands**:
- ✅ Multiple operations on the same file (load once, modify multiple times, save once)
- ✅ Complex refactoring requiring multiple related changes
- ✅ When you need to explore tree structure before making changes
- ✅ When atomicity across multiple operations is critical

**When to use Traditional CST Commands**:
- ✅ Single operation on a file (compose_cst_module is simpler)
- ✅ Quick edits without needing tree exploration
- ✅ When you don't need to keep tree in memory

### 6.6 Code Quality Commands

- `format_code` - Format with black
- `lint_code` - Lint with flake8
- `type_check_code` - Type check with mypy

### 6.7 Utility Commands

- `update_indexes` - Full project scan to (re)build indexes; use when needed (e.g. initial setup or out-of-sync). Saving via `cst_save_tree`/`compose_cst_module` updates indexes for the saved file automatically.
- `get_imports` - Get imports
- `find_dependencies` - Find dependencies
- `get_class_hierarchy` - Get class hierarchy

### 6.8 Comprehensive Analysis Commands

- `comprehensive_analysis` - Comprehensive code quality analysis combining:
  - Placeholders (TODO, FIXME, etc.)
  - Stubs (pass, ellipsis, NotImplementedError)
  - Empty methods (excluding abstract)
  - Imports not at top of file
  - Long files (>400 lines)
  - Code duplicates (structural and semantic)
  - Flake8 linting errors
  - Mypy type checking errors

## 7. Error Handling Rules

### 7.1 When Errors Occur

**Rule**: Always investigate and fix errors immediately.

**Process**:
1. ✅ Read error message carefully
2. ✅ Check server logs (`logs/mcp_server.log`)
3. ✅ Verify file syntax
4. ✅ Check imports and dependencies
5. ✅ Restart server if needed
6. ✅ Fix the issue before continuing

**Never**:
- ❌ Ignore errors
- ❌ Skip validation
- ❌ Continue with broken code

### 7.2 Common Error Patterns

**Docstring Validation Errors**:
- Missing file-level docstring
- Missing class docstring
- Missing method docstring
- Missing parameter descriptions
- Missing attribute descriptions
- Missing type hints

**Solution**: Add required docstrings and type hints.

**Compilation Errors**:
- Syntax errors in new code
- Import errors
- Type errors

**Solution**: Fix syntax/imports, run type checker.

### 7.3 CST Error Fallback Table

When a CST command fails, use this table to choose an alternative. Full task→command→fallback guidance: [CST_WORKFLOW_GUIDE.md](CST_WORKFLOW_GUIDE.md).

| Error | Try instead | Example |
|-------|-------------|---------|
| `cst_modify_tree` "was not replaced" (e.g. SimpleStatementLine in Module.body) | `query_cst` with `replace_with` or `code_lines` | `query_cst(project_id, file_path, selector="ImportFrom", match_index=0, replace_with="from foo import bar")` |
| `query_cst` returns no matches | Check selector syntax; try a simpler selector (e.g. `ImportFrom`, `function[name='x']`) | Use query-only first: `query_cst(..., include_code=true)` to verify matches |
| `cst_load_file` fails (syntax error in file) | `replace_file_lines` to fix the broken range | `replace_file_lines(project_id, file_path, start_line, end_line, new_lines)` then retry `cst_load_file` |
| `compose_cst_module` validation/docstring errors | Fix code to satisfy validation, or use `cst_load_file` → `cst_modify_tree` → `cst_save_tree` | Ensure docstrings and type hints in `new_code`; tree path may give different validation behavior |
| Need multiple edits in one file | Prefer `cst_load_file` → `cst_modify_tree` (multiple ops) → `cst_save_tree` | Single atomic save; avoid multiple `compose_cst_module` calls for the same file |

## 8. Code Writing Standards

### 8.1 Docstring Requirements

**CRITICAL**: All code must have proper docstrings:

1. **File-level docstring** (required):
   ```python
   """
   Module description.
   
   Author: Vasiliy Zdanovskiy
   email: vasilyvz@gmail.com
   """
   ```

2. **Class docstring** (required):
   ```python
   class MyClass:
       """
       Class description.
       
       Attributes:
           attr1: Description of attr1
           attr2: Description of attr2
       """
   ```

3. **Method docstring** (required):
   ```python
   def method(self, param1: int, param2: str) -> bool:
       """
       Method description.
       
       Args:
           param1: Description of param1
           param2: Description of param2
       
       Returns:
           Description of return value
       """
   ```

### 8.2 Type Hints

**Rule**: All functions/methods must have:
- ✅ Type hints for all parameters (except `self`/`cls`)
- ✅ Return type hint (except `__init__`)

**Example**:
```python
# ✅ CORRECT
def process_data(data: dict[str, Any], count: int) -> list[str]:
    ...

# ❌ WRONG
def process_data(data, count):
    ...
```

### 8.3 Import Organization

**Rule**: Imports are automatically normalized by `compose_cst_module`.

**Manual organization**:
1. Standard library imports
2. Third-party imports
3. Local imports

## 9. Workflow Examples

### 9.1 Creating New Module

```python
# 1. Create module with compose_cst_module
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/path",
        "file_path": "new_module.py",
        "ops": [{
            "selector": {"kind": "module"},
            "file_docstring": "New module description",
            "new_code": "class NewClass:\n    \"\"\"Class description.\"\"\"\n    pass"
        }],
        "apply": True
    }
)

# 2. Validate
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="format_code",
    params={"file_path": "new_module.py"}
)
# Indexes for the file are updated automatically when saving via CST. Run update_indexes only if needed (e.g. initial project setup).
```

### 9.2 Modifying Existing Code (CRITICAL: Use CST)

**ALWAYS use CST tools for existing code. Never use `search_replace` or direct editing.**

**Two approaches available:**
1. **Traditional file-based CST** (simpler for single operations) - see below
2. **In-memory tree-based CST** (better for multiple operations) - see section 9.2.1

```python
# Step 1: Discover blocks to understand structure
blocks_result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="list_cst_blocks",
    params={"root_dir": "/path", "file_path": "file.py"}
)
# Returns: {"blocks": [{"id": "function:my_func:10-20", "kind": "function", ...}]}

# Step 2 (optional): Query for specific nodes if needed
query_result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="query_cst",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "selector": "function[name='my_func'] smallstmt[type='Return']"
    }
)
# Returns: {"matches": [{"node_id": "...", "kind": "smallstmt", ...}]}

# Step 3: Preview changes (recommended)
preview_result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "ops": [{
            "selector": {"kind": "block_id", "block_id": "function:my_func:10-20"},
            # OR: {"kind": "method", "name": "MyClass.method"},
            # OR: {"kind": "cst_query", "query": "function[name='my_func']"},
            "new_code": "def my_func(param: int) -> str:\n    \"\"\"Updated function.\"\"\"\n    return str(param)"
        }],
        "apply": False,  # Preview only
        "return_diff": True,
        "return_source": False
    }
)
# Check preview_result["data"]["diff"] before applying

# Step 4: Apply changes
result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "ops": [{
            "selector": {"kind": "block_id", "block_id": "function:my_func:10-20"},
            # For multi-line code, new_code is a single string (compose_cst_module handles it)
            "new_code": "def my_func(param: int) -> str:\n    \"\"\"Updated function.\"\"\"\n    return str(param)"
        }],
        "apply": True,
        "create_backup": True,
        "return_diff": True
    }
)

# Step 5: Validate and restart
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="format_code",
    params={"file_path": "file.py"}
)

# Step 6: Run comprehensive analysis (after logically completed step)
comprehensive_result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="comprehensive_analysis",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "check_placeholders": True,
        "check_stubs": True,
        "check_empty_methods": True,
        "check_imports": True,
        "check_long_files": True,
        "check_duplicates": True,
        "check_flake8": True,
        "check_mypy": True
    },
    use_queue=True
)

# Get results when job completes
if comprehensive_result.get("result", {}).get("queued"):
    job_id = comprehensive_result["result"]["job_id"]
    # Poll for results
    import time
    while True:
        status = mcp_MCP-Proxy-2_call_server(
            server_id="code-analysis-server",
            command="queue_get_job_status",
            params={"job_id": job_id}
        )
        if status["result"]["data"]["status"] == "completed":
            analysis_results = status["result"]["data"]["result"]["result"]["data"]
            # Review and fix issues found in analysis_results
            break
        elif status["result"]["data"]["status"] == "failed":
            # Handle error
            break
        time.sleep(1)

# Restart server if code changed
run_terminal_cmd("cd /path && source .venv/bin/activate && python -m code_analysis.cli.server_manager_cli --config config.json restart")
```

### 9.2.1 Modifying Existing Code with In-Memory CST Trees (NEW)

**Use tree-based approach when:**
- ✅ Multiple related operations on the same file
- ✅ Need to explore tree structure before making changes
- ✅ Want atomicity across all modifications
- ✅ Complex refactoring requiring multiple steps

**Workflow**:
```python
# Step 1: Load file into CST tree
load_result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="cst_load_file",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "include_children": True,  # Include children in metadata
        "node_types": ["FunctionDef", "ClassDef"],  # Optional: filter by types
        "max_depth": 3  # Optional: limit depth
    }
)
tree_id = load_result["result"]["data"]["tree_id"]

# Step 2: Find nodes to modify (optional - can use node_id from load_result)
# Option A: Find by search (XPath or simple)
find_result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="cst_find_node",
    params={
        "tree_id": tree_id,
        "search_type": "xpath",  # or "simple"
        "query": "function[name='my_func']"  # XPath selector
        # OR for simple search:
        # "search_type": "simple",
        # "node_type": "FunctionDef",
        # "name": "my_func"
    }
)
node_id = find_result["result"]["data"]["matches"][0]["node_id"]

# Option B: Get node by line range (when you know line numbers)
# range_result = mcp_MCP-Proxy-2_call_server(
#     server_id="code-analysis-server",
#     command="cst_get_node_by_range",
#     params={
#         "tree_id": tree_id,
#         "start_line": 136,  # 1-based, inclusive
#         "end_line": 143,    # 1-based, inclusive
#         "prefer_exact": False,  # True: prefer exact match, False: smallest containing node
#         "all_intersecting": False  # True: return all intersecting nodes, False: single best node
#     }
# )
# node_id = range_result["result"]["data"]["node"]["node_id"]

# Step 3: Get node information (optional - to see current code)
node_info = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="cst_get_node_info",
    params={
        "tree_id": tree_id,
        "node_id": node_id,
        "include_code": True,  # Include code snippet
        "include_children": True,  # Include children
        "include_parent": True,  # Include parent
        "max_children": 10  # Limit children count
    }
)

# Step 4: Modify tree (can apply multiple operations atomically)
modify_result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="cst_modify_tree",
    params={
        "tree_id": tree_id,
        "operations": [
            {
                "action": "replace",  # or "insert", "delete"
                "node_id": node_id,
                # For multi-line code, use code_lines (RECOMMENDED) to avoid JSON escaping issues
                "code_lines": [
                    "def my_func(param: int) -> str:",
                    "    \"\"\"Updated function.\"\"\"",
                    "    return str(param)"
                ]
                # OR use code for single-line (legacy, works but may have escaping issues):
                # "code": "def my_func(param: int) -> str:\n    \"\"\"Updated function.\"\"\"\n    return str(param)"
            },
            # Can add more operations here - all validated together
            # {
            #     "action": "insert",
            #     "target_node_id": "node_id_to_insert_after",  # Insert after specific node
            #     # OR: "parent_node_id": "parent_node_id",  # Insert at beginning/end of parent
            #     "position": "after",  # or "before"
            #     "code_lines": [
            #         "def new_function():",
            #         "    \"\"\"New function.\"\"\"",
            #         "    pass"
            #     ]
            # }
        ]
    }
)
# All operations are validated together - if any fails, tree remains unchanged

# Step 5: Save tree to file (atomic operation with backup)
save_result = mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="cst_save_tree",
    params={
        "tree_id": tree_id,
        "root_dir": "/path",
        "file_path": "file.py",
        "project_id": "project-uuid",  # Required
        "validate": True,  # Validate before saving
        "backup": True,  # Create backup before saving
        "commit_message": "Updated my_func"  # Optional: git commit message
    }
)
# This operation is fully atomic:
# 1. Validates original file
# 2. Creates backup
# 3. Writes to temp file
# 4. Validates temp file
# 5. Atomically replaces original
# 6. Updates database
# 7. On any error: rollback and restore backup
# Note: Backup (old_code) is mandatory before write. commit_message is optional (git commit after save).

# Step 6: Validate and analyze (same as traditional approach)
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="format_code",
    params={"file_path": "file.py"}
)

mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="comprehensive_analysis",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "check_placeholders": True,
        "check_stubs": True,
        "check_empty_methods": True,
        "check_imports": True,
        "check_long_files": True,
        "check_duplicates": True,
        "check_flake8": True,
        "check_mypy": True
    },
    use_queue=True
)
```

**Key Advantages of Tree-based Approach**:
- ✅ **Atomicity**: All modifications validated together before saving
- ✅ **Efficiency**: Load file once, modify multiple times, save once
- ✅ **Exploration**: Can explore tree structure before making changes
- ✅ **Safety**: Full rollback on any error during save
- ✅ **Database Integration**: Automatic database update after save

**Operation Types for `cst_modify_tree`**:
- `"replace"` - Replace node with new code
  - Requires: `node_id`, `code` OR `code_lines`
  - `code_lines` (array of strings) is RECOMMENDED for multi-line code to avoid JSON escaping issues
- `"insert"` - Insert new code
  - Requires: (`parent_node_id` OR `target_node_id`), `position` ("before" or "after", or `first`/`last`/`{"after": N}`), `code` OR `code_lines`
  - `target_node_id`: Insert before/after specific node (automatically finds parent)
  - `parent_node_id`: Must be a **container** node: **Module**, **FunctionDef**, or **ClassDef** — not the body node (IndentedBlock). Use **`__root__`** for module-level insert. To insert into a function body, use the **function's node_id** (FunctionDef), not its IndentedBlock child. See `docs/commands/cst/cst_modify_tree.md` for details.
  - `code_lines` (array of strings) is RECOMMENDED for multi-line code
- `"delete"` - Delete node
  - Requires: `node_id` only (code not needed)

**Code Format for Operations**:
- **`code_lines` (RECOMMENDED for multi-line)**: Array of strings, each line is separate element
  - ✅ No JSON escaping issues (`\n`, `\t`, `"`, emoji, etc.)
  - ✅ Preserves exact formatting (indentation, empty lines)
  - ✅ Easier to work with in JSON/MCP
  - Example: `["line1", "    line2", "", "    line3"]`
- **`code` (legacy, single-line only)**: Single string with `\n` for newlines
  - ⚠️ May have escaping issues with special characters
  - ⚠️ Less convenient for multi-line code
  - Example: `"line1\n    line2\n\n    line3"`

**Search Types for `cst_find_node`**:
- `"xpath"` - Use CSTQuery XPath-like selectors (powerful, flexible)
- `"simple"` - Simple search by type, name, qualname, or line range

**Selector Types for `compose_cst_module`**:
- `{"kind": "block_id", "block_id": "..."}` - Use stable ID from `list_cst_blocks`
- `{"kind": "function", "name": "func_name"}` - Find by function name
- `{"kind": "class", "name": "ClassName"}` - Find by class name
- `{"kind": "method", "name": "ClassName.method"}` - Find by qualified method name
- `{"kind": "node_id", "node_id": "..."}` - Use node ID from `query_cst`
- `{"kind": "cst_query", "query": "..."}` - Use CSTQuery selector string
- `{"kind": "range", "start_line": 10, "end_line": 20}` - Replace the **statement** whose LibCST line span equals that inclusive 1-based range; **blank lines above** that statement are preserved (important for import-line edits and spacing before classes). Optional `start_col` / `end_col` for an exact character span (e.g. after resolving `node_id`).

### 9.3 Refactoring Large File

**CRITICAL**: Always use MCP splitting tools, never split manually!

```python
# 1. Check file size
run_terminal_cmd("wc -l code_analysis/core/large_file.py")

# 2. Analyze structure
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="list_cst_blocks",
    params={"root_dir": "/path", "file_path": "large_file.py"}
)

# 3. Split file using MCP command (REQUIRED - allows parallel testing)
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="split_file_to_package",
    params={
        "root_dir": "/path",
        "file_path": "large_file.py",
        "config_path": "data/refactor_configs/split_config.json"
    }
)

# Indexes are updated automatically when saving via CST. Run update_indexes only when needed (e.g. initial project setup or out-of-sync).
```

**Why MCP splitting?**
- ✅ Preserves code structure and relationships
- ✅ Automatic testing during refactoring
- ✅ Maintains imports and dependencies
- ✅ Better code quality and consistency
- ❌ Manual splitting breaks these guarantees

## 10. Code Writing Technology Rules

### 10.1 Core Principle: Code as Tree Nodes, Not Text

**CRITICAL**: Code modifications work with **CST tree nodes**, not raw text strings.

**Why Tree-based Approach**:
- ✅ **Syntax validation**: Code is parsed before applying - invalid syntax is caught early
- ✅ **Structure preservation**: Formatting, comments, and structure are preserved
- ✅ **Atomic operations**: All changes validated together, rollback on any error
- ✅ **No escaping issues**: `code_lines` (array) avoids JSON escaping problems
- ✅ **Database consistency**: Changes tracked in database automatically

### 10.2 Multi-line Code Format

**RECOMMENDED**: Use `code_lines` (array of strings) for multi-line code:

```json
{
  "action": "replace",
  "node_id": "stmt:main:SimpleStatementLine:136:8-136:46",
  "code_lines": [
    "engine = ServerEngineFactory.get_engine(\"hypercorn\")",
    "if not engine:",
    "    print(\"❌ Error\", file=sys.stderr)",
    "    sys.exit(1)",
    "",
    "# Prepare server configuration",
    "server_config = {",
    "    \"host\": config.model.server.host,",
    "    \"port\": config.model.server.port,",
    "    \"log_level\": \"info\",",
    "    \"reload\": False,",
    "}",
    "",
    "engine.run_server(app, server_config)"
  ]
}
```

**Advantages of `code_lines`**:
- ✅ No JSON escaping issues (`\n`, `\t`, `"`, emoji, unicode)
- ✅ Preserves exact formatting (indentation, empty lines)
- ✅ Each line is separate array element - easy to work with
- ✅ No need to escape special characters

**Legacy `code` (single string)** - Use only for single-line:
```json
{
  "action": "replace",
  "node_id": "stmt:main:SimpleStatementLine:10:0-10:20",
  "code": "x = 42"
}
```

### 10.3 Test Project Code Modification Rules

**CRITICAL**: For test projects (e.g., `test_data/particles/`), code modifications **MUST** be done **ONLY** through server tools:

- ✅ **MANDATORY**: Use `cst_load_file` → `cst_modify_tree` → `cst_save_tree`
- ✅ **MANDATORY**: Use `compose_cst_module` for single operations
- ❌ **FORBIDDEN**: Direct file editing (`search_replace`, `write`) for test project code
- ❌ **FORBIDDEN**: Manual file modifications

**Rationale**: Test projects are used to test server functionality. Modifying them directly bypasses server validation and testing.

### 10.4 Code Writing Workflow

**For existing code (MANDATORY workflow)**:

1. **Load/Discover**:
   - Tree-based: `cst_load_file` → get `tree_id`
   - Traditional: `list_cst_blocks` → get block IDs

2. **Explore/Find**:
   - Tree-based: `cst_find_node` → find nodes to modify (or `cst_get_node_by_range` if you know line numbers)
   - Traditional: `query_cst` → find specific nodes

3. **Inspect** (optional but recommended):
   - Tree-based: `cst_get_node_info` → see current code, children, parent
   - Traditional: Use block info from `list_cst_blocks`

4. **Modify**:
   - Tree-based: `cst_modify_tree` with `code_lines` for multi-line code
   - Traditional: `compose_cst_module` with `new_code` string

5. **Save**:
   - Tree-based: `cst_save_tree` → atomic save with backup
   - Traditional: `compose_cst_module` with `apply=true` → saves automatically

6. **Validate**:
   - `format_code`, `lint_code`, `type_check_code`
   - `comprehensive_analysis` after logically completed steps

## 11. Best Practices Summary

### 11.1 Always Do

- ✅ Use MCP commands as primary interface
- ✅ **Use CST tools for ALL existing code modifications**
  - **Traditional**: `compose_cst_module` for single operations
  - **Tree-based**: `cst_load_file` → `cst_modify_tree` → `cst_save_tree` for multiple operations
- ✅ **Use `code_lines` (array) for multi-line code** - avoids JSON escaping issues
- ✅ **Use `list_cst_blocks` and `query_cst` to discover code structure before editing** (traditional)
- ✅ **Use `cst_load_file` and `cst_find_node` (or `cst_get_node_by_range`) to explore tree structure** (tree-based)
- ✅ Preview changes with `apply=false` and `return_diff=true` before applying (traditional)
- ✅ Use `cst_get_node_info` to inspect nodes before modifying (tree-based)
- ✅ **For test projects: ONLY use server tools, NEVER direct file editing**
- ✅ **Run `comprehensive_analysis` after each logically completed step**
- ✅ Validate code before committing
- ✅ Follow file organization standards
- ✅ Keep files under 400 lines
- ✅ Add proper docstrings and type hints
- ✅ Restart server after code changes
- ✅ Indexes update automatically when saving via `cst_save_tree`/`compose_cst_module`; run `update_indexes` only when needed (e.g. initial setup or out-of-sync)
- ✅ Use direct write (`write` tool) ONLY for new files

### 11.2 Never Do

- ❌ **Use `search_replace` or direct editing for existing Python code** (use CST tools!)
- ❌ **Edit existing code without first using `list_cst_blocks` or `query_cst`**
- ❌ Use CLI when MCP is available
- ❌ Skip validation
- ❌ Ignore errors
- ❌ Create files in wrong directories
- ❌ Exceed 400 lines per file
- ❌ Skip docstrings
- ❌ Skip type hints
- ❌ Continue with broken code
- ❌ **Manually split large files** (always use MCP splitting tools)

## 12. Quick Reference

### 12.1 Command Priority

1. **MCP** → `mcp_MCP-Proxy-2_call_server`
2. **CLI** → `run_terminal_cmd` (fallback only)

### 12.2 Code Editing Priority

1. **Existing Python code** → **CST tools** (via MCP) - **REQUIRED**
   - **Single operation**: `compose_cst_module` (traditional)
   - **Multiple operations**: `cst_load_file` → `cst_modify_tree` → `cst_save_tree` (tree-based)
2. **New Python files** → Direct write (`write` tool)
3. **Non-Python files** → Direct editing (`write`, `search_replace`)

**CST Workflow (Traditional - for single operations)**:
1. `list_cst_blocks` → discover structure
2. `query_cst` (optional) → find specific nodes
3. `compose_cst_module` with `apply=false` → preview
4. `compose_cst_module` with `apply=true` → apply

**CST Workflow (Tree-based - for multiple operations)**:
1. `cst_load_file` → load file into tree (get tree_id)
2. `cst_find_node` → find nodes (simple or XPath search)
   - OR `cst_get_node_by_range` → get node_id by line range (when you know line numbers)
3. `cst_get_node_info` (optional) → inspect node details
4. `cst_modify_tree` → apply multiple operations atomically
   - Use `code_lines` (array) for multi-line code (RECOMMENDED)
   - Use `code` (string) only for single-line code
5. `cst_save_tree` → atomically save with backup and validation

### 12.3 Validation

- **Automatic** → `compose_cst_module` validates automatically
- **Manual** → `format_code`, `lint_code`, `type_check_code`

### 12.4 After Changes

1. Format code
2. Lint code
3. Type check
4. **Run comprehensive analysis** (after each logically completed step)
5. Restart server (if code in `code_analysis/` changed). Indexes are updated automatically on CST save; run `update_indexes` only when needed (e.g. initial project setup).

---

**Remember**: This project is a tool for AI. The goal is not just writing code, but creating a tool that works primarily through MCP. CLI is just a fallback option.

