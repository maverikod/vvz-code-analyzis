# query_cst

**Command name:** `query_cst`  
**Class:** `QueryCSTCommand`  
**Source:** `code_analysis/commands/query_cst_command.py`  
**Category:** cst

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

---

## Purpose (Предназначение)

The query_cst command queries Python source code using CSTQuery selectors to locate specific LibCST nodes. It provides a jQuery/XPath-like selector language for finding nodes while preserving formatting and comments.

Operation flow:
1. Validates root_dir exists and is a directory
2. Resolves file_path (absolute or relative to root_dir)
3. Validates file is a .py file
4. Validates file exists
5. Reads file source code
6. Parses source using LibCST
7. Applies CSTQuery selector to find matching nodes
8. Generates node IDs for each match
9. Optionally includes code snippets
10. Limits results to max_results if specified
11. Returns list of matches with metadata

CSTQuery Selector Syntax:
- Selectors are sequences of steps connected by combinators
- Descendant combinator: whitespace (A B finds B inside A)
- Child combinator: > (A > B finds B as direct child of A)
- Each step: TYPE or * with optional predicates and pseudos
- Predicates: [attr OP value] (e.g., [name="MyClass"])
- Pseudos: :first, :last, :nth(N)

Supported TYPE Aliases:
- module, class, function, method, stmt, smallstmt, import, node
- LibCST node class names: If, For, Try, With, Return, Assign, Call, etc.

Predicate Operators:
- = exact equality
- != not equal
- ~= substring match
- ^= prefix match
- $= suffix match

Supported Attributes:
- type: LibCST node type
- kind: Node kind (stmt, smallstmt, class, function, method, etc.)
- name: Node name (for named nodes)
- qualname: Qualified name (for methods: ClassName.method)
- start_line, end_line: Line numbers

Node Information:
- node_id: Stable-enough identifier (span-based) for compose_cst_module
- kind: Node kind classification
- type: LibCST node type
- name: Node name (if applicable)
- qualname: Qualified name (if applicable)
- start_line, start_col: Starting position
- end_line, end_col: Ending position
- code: Code snippet (if include_code=True)

Use cases:
- Find specific nodes by type or name
- Locate statements, expressions, or declarations
- Discover code patterns
- Find nodes for refactoring operations
- Analyze code structure
- Prepare for compose_cst_module operations

Typical Workflow:
1. Use query_cst to find target nodes
2. Get node_id from matches
3. Use compose_cst_module with selector kind='node_id' or kind='cst_query'
4. Preview diff and compile result
5. Apply changes if satisfied

Important notes:
- Selector syntax follows CSTQuery rules (see docs/CST_QUERY.md)
- node_id is span-based and stable enough for patch workflows
- Results can be truncated if max_results limit is reached
- include_code=True can make response large for many matches
- Use max_results to limit output size
- Line numbers are 1-based
- Column numbers are 0-based

---

## Arguments (Аргументы)

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | No | Project ID (UUID4). If provided, root_dir will be resolved from database. Either project_id or root_dir must be provided. |
| `root_dir` | string | No | Project root directory. Required if project_id is not provided. |
| `file_path` | string | **Yes** | Target python file path (relative to project root) |
| `selector` | string | **Yes** | CSTQuery selector string |
| `include_code` | boolean | No | If true, include code snippets for each match (can be large) Default: `false`. |
| `max_results` | integer | No | Maximum number of matches to return Default: `200`. |

**Schema:** `additionalProperties: false` — only the parameters above are accepted.

---

## Returned data (Возвращаемые данные)

All MCP commands return either a **success** result (with `data`) or an **error** result (with `code` and `message`).

### Success

- **Shape:** `SuccessResult` with `data` object.
- `success`: Always True on success
- `file_path`: Path to queried file
- `selector`: Selector string that was used
- `truncated`: True if results were truncated due to max_results
- `matches`: List of match dictionaries. Each contains:
- node_id: Stable identifier for compose_cst_module
- kind: Node kind (stmt, smallstmt, class, function, method, etc.)
- type: LibCST node type (If, Return, ClassDef, FunctionDef, etc.)
- name: Node name (if applicable)
- qualname: Qualified name (if applicable)
- start_line, start_col: Starting position (1-based line, 0-based col)
- end_line, end_col: Ending position (1-based line, 0-based col)
- code: Code snippet (if include_code=True)

### Error

- **Shape:** `ErrorResult` with `code` and `message`.
- **Possible codes:** INVALID_FILE, FILE_NOT_FOUND, CST_QUERY_PARSE_ERROR, CST_QUERY_ERROR (and others).

---

## Examples

### Correct usage

**Find class by exact name**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/main.py",
  "selector": "class[name=\"MyClass\"]"
}
```

Finds all classes named exactly 'MyClass' in main.py. Returns node_id that can be used with compose_cst_module.

**Find class by name prefix**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/models.py",
  "selector": "class[name^=\"Base\"]"
}
```

Finds all classes whose names start with 'Base' (e.g., BaseModel, BaseView). Uses prefix match operator (^=).

**Find class by name suffix**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/handlers.py",
  "selector": "class[name$=\"Handler\"]"
}
```

Finds all classes whose names end with 'Handler' (e.g., RequestHandler, EventHandler). Uses suffix match operator ($=).

**Find class by name substring**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/services.py",
  "selector": "class[name~=\"Service\"]"
}
```

Finds all classes whose names contain 'Service' (e.g., UserService, PaymentService). Uses substring match operator (~=).

**Find all return statements**
```json
{
  "root_dir": "/home/user/projects/my_project",
  "file_path": "src/utils.py",
  "selector": "smallstmt[type=\"Return\"]"
}
```

Finds all return statements in utils.py. Useful for analyzing control flow and finding early returns.

### Incorrect usage

- **INVALID_FILE**: File is not a Python file. Ensure file_path points to a .py file

- **FILE_NOT_FOUND**: File does not exist. Verify file_path is correct and file exists

- **CST_QUERY_PARSE_ERROR**: Invalid selector syntax. Check selector syntax. Ensure:
- Proper predicate syntax: [attr OP value]
- Valid operators: =, !=, ~=, ^=, $=
- Valid pseudos: :first, :last, :nth(N)
- Proper combinator usage: whitespace or >
See docs/CST_QUERY.md for syntax reference.

- **CST_QUERY_ERROR**: Error during query execution. 

## Error codes summary

| Code | Description | Action |
|------|-------------|--------|
| `INVALID_FILE` | File is not a Python file | Ensure file_path points to a .py file |
| `FILE_NOT_FOUND` | File does not exist | Verify file_path is correct and file exists |
| `CST_QUERY_PARSE_ERROR` | Invalid selector syntax | Check selector syntax. Ensure:
- Proper predicate  |
| `CST_QUERY_ERROR` | Error during query execution |  |

## Best practices

- Use query_cst to find specific nodes before compose_cst_module
- Save node_id from matches for use in compose_cst_module
- Use include_code=True only when needed (can be large)
- Set max_results to limit output size for broad queries
- Check truncated field to see if results were limited
- Use specific selectors to find exact nodes
- Combine selectors with combinators for complex queries
- Use pseudos (:first, :last, :nth) to select specific matches

---
