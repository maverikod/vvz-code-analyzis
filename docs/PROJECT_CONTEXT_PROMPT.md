# Project Context and Work Rules - AI Model Prompt

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Purpose**: Clear instructions for AI models working on this project

---

## 🎯 Project Overview

This is an **MCP (Model Context Protocol) server** that provides tools for Python code analysis, refactoring, and quality checking.

### Core Technologies
- **CST (Concrete Syntax Tree)**: Primary method for code manipulation using LibCST
- **AST (Abstract Syntax Tree)**: Used for code analysis and entity extraction
- **Test Data**: Located in `test_data/` directory with example projects

### Project Structure
- `code_analysis/` - Main source code of the MCP server
- `test_data/` - Test projects for validating server tools
- `tests/` - Pytest test suite
- `docs/` - All documentation
- `scripts/` - Utility scripts (non-pytest)

---

## 🎯 PRIMARY GOALS (Priority Order)

### 1. MAIN GOAL: Tool Development and Debugging ⭐ HIGHEST PRIORITY

**The primary objective is to write and debug code using the server's tools to identify errors and inaccuracies in tool functionality.**

- Focus on **testing and improving the server tools themselves**
- Use test projects in `test_data/` to validate tool behavior
- Identify bugs, edge cases, and limitations in the tools
- Report tool errors immediately when discovered

**This is more important than writing production code in test projects.**

### 2. Secondary Goal: Real-World Code Usage

- Code written may be used in real projects
- However, **writing code in test projects is NOT the main objective**
- Test projects serve as validation targets for the tools

### 3. Error Reporting: IMMEDIATE

**When an error is discovered:**
- ✅ **Report immediately** - Do not wait to finish current task
- ✅ Provide clear error description
- ✅ Include context (which tool, what operation, error message)
- ✅ Suggest potential fixes if possible

### 4. Tool Usage Restrictions

#### For Test Projects (`test_data/`)

**MANDATORY: Use ONLY server tools (MCP commands)**

- ✅ Allowed: MCP server commands (`compose_cst_module`, `query_cst`, `format_code`, `lint_code`, `type_check_code`, etc.)
- ❌ Forbidden: Direct file editing tools (`search_replace`, `write`) for existing Python files
- ❌ Forbidden: External tools (black, flake8, mypy) without explicit user permission
- ✅ Exception: Creating NEW files from scratch (can use `write`)

**Rationale**: Test projects are used to validate server tools. Using external tools defeats the purpose.

#### For Project Code (`code_analysis/`)

**ALLOWED: Any tools can be used**

- ✅ MCP server commands
- ✅ Direct file editing (`search_replace`, `write`)
- ✅ External tools (black, flake8, mypy, pytest, etc.)
- ✅ Standard Python development tools

**Rationale**: The project code itself needs to be maintained and improved using standard development practices.

---

## 📋 Workflow Rules

### When Working on Test Projects (`test_data/`)

1. **Use server tools exclusively**:
   - `compose_cst_module` for code editing
   - `query_cst` / `list_cst_blocks` for code discovery
   - `format_code`, `lint_code`, `type_check_code` for validation
   - `comprehensive_analysis` for code analysis

2. **If server tool fails**:
   - Report error immediately to user
   - Wait for user decision (retry, use fallback, cancel)
   - Do NOT automatically switch to direct file editing

3. **If you discover a tool bug**:
   - Report immediately (don't wait to finish task)
   - Document the issue clearly
   - Suggest workaround if possible

### When Working on Project Code (`code_analysis/`)

1. **Use any appropriate tools**:
   - Server tools when available and suitable
   - Direct file editing when needed
   - External tools (black, flake8, mypy) for code quality

2. **Follow project standards**:
   - Run `black`, `flake8`, `mypy` after code changes
   - Run `code_mapper` to update indexes after changes
   - Follow file organization rules (see `.cursorrules`)

---

## 🚨 Critical Rules Summary

### DO ✅

1. **Prioritize tool testing and debugging** over writing test project code
2. **Report errors immediately** when discovered
3. **Use only server tools** when working in `test_data/`
4. **Use any tools** when working in `code_analysis/`
5. **Wait for user approval** before using fallback tools
6. **Document tool issues** clearly when found

### DON'T ❌

1. **Don't silently switch** from server tools to direct editing
2. **Don't use external tools** in `test_data/` without permission
3. **Don't wait** to report errors until task completion
4. **Don't assume** tool behavior - test and validate
5. **Don't skip** error reporting

---

## 🔍 Understanding the Context

### Why Test Projects Exist

Test projects in `test_data/` are **not meant to be production code**. They are:
- Validation targets for server tools
- Bug reproduction environments
- Edge case testing scenarios
- Tool behavior verification

### Why Tool Development is Priority #1

The MCP server provides tools for Python code manipulation. These tools must be:
- Reliable and accurate
- Handle edge cases correctly
- Provide clear error messages
- Maintain code quality standards

**Finding and fixing tool bugs is more valuable than writing test project code.**

### Why Different Rules for Different Directories

- **`test_data/`**: Must use server tools to validate them
- **`code_analysis/`**: Can use any tools to maintain project quality

---

## 📝 Example Scenarios

### Scenario 1: Working on Test Project

**Task**: Add a new function to a test file in `test_data/`

**Correct approach**:
1. Use `list_cst_blocks` to discover file structure
2. Use `compose_cst_module` with `apply=false` to preview changes
3. Use `compose_cst_module` with `apply=true` to apply changes
4. Use `format_code`, `lint_code`, `type_check_code` to validate
5. If any tool fails → Report immediately to user

**Incorrect approach**:
- ❌ Using `search_replace` to edit the file directly
- ❌ Running `black` or `flake8` directly on the file
- ❌ Continuing work after discovering a tool error

### Scenario 2: Working on Project Code

**Task**: Fix a bug in `code_analysis/commands/cst_compose_module_command.py`

**Correct approach**:
1. Can use `search_replace` or `write` for direct editing
2. Can use `black`, `flake8`, `mypy` for validation
3. Can use server tools if appropriate
4. Run `code_mapper` to update indexes
5. Report any issues found

### Scenario 3: Discovering a Tool Error

**Situation**: `compose_cst_module` returns an unexpected error

**Correct approach**:
1. ✅ **Stop current work immediately**
2. ✅ **Report error to user immediately**:
   - Which command failed
   - What operation was attempted
   - Exact error message
   - Context (file, operation type)
3. ✅ **Wait for user decision**:
   - Should we retry?
   - Should we use fallback?
   - Should we investigate further?

**Incorrect approach**:
- ❌ Silently switching to `search_replace`
- ❌ Continuing with other tasks
- ❌ Trying to work around the error without reporting

---

## 🎓 Key Takeaways

1. **Tool development > Test project code**
2. **Report errors immediately**
3. **Test projects = Server tools only**
4. **Project code = Any tools allowed**
5. **Always wait for user approval on errors**

---

## 📚 Related Documentation

- `docs/AI_TOOL_USAGE_RULES.md` - Detailed tool usage rules
- `.cursorrules` - File organization standards
- `docs/CST_ATOMICITY_ANALYSIS.md` - CST operation analysis

---

**Remember**: This is a tool development project. Finding and fixing tool bugs is the primary goal. Test projects are means to that end, not ends in themselves.
