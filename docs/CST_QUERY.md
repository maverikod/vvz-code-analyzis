## CSTQuery (LibCST selectors)

CSTQuery is a small selector language (jQuery/XPath-like) for locating Python CST nodes
while preserving formatting and comments (via **LibCST**).

It is implemented as a standalone package: `code_analysis/cst_query/`, so it can be
extracted into a separate library later if needed.

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

### MCP command: `query_cst`

Use this command to **find nodes** in a Python file.

Inputs:
- `root_dir`: project root
- `file_path`: target `.py`
- `selector`: CSTQuery selector string
- `include_code` (optional): include matched node code snippets
- `max_results` (optional): cap output size

Output:
- `matches[]`: each match contains:
  - `node_id`: stable-enough id (span-based) for patch workflows
  - `kind`: `stmt | smallstmt | class | function | method | import | node`
  - `type`: LibCST node type (e.g. `If`, `Return`, `ClassDef`, `FunctionDef`)
  - `name`, `qualname` (when applicable)
  - `start_line`, `start_col`, `end_line`, `end_col`

### Selector syntax

A selector is a sequence of **steps** connected by **combinators**:

- **descendant**: whitespace (`A B`)
- **child**: `>` (`A > B`)

Each step is:

- `TYPE` or `*`
- optional predicates: `[attr OP value]`
- optional pseudos: `:first`, `:last`, `:nth(N)`

Examples:

- Find a class by name:
  - `class[name="MyClass"]`
- Find a method by qualified name:
  - `method[qualname="MyClass.my_method"]`
- Find all `return` statements in a file:
  - `smallstmt[type="Return"]`
- Find the first return in a specific function:
  - `function[name="f"] smallstmt[type="Return"]:first`
- Find the 2nd return (0-based):
  - `smallstmt[type="Return"]:nth(1)`

### Supported TYPE aliases

- `module`, `class`, `function`, `method`, `stmt`, `smallstmt`, `import`, `node`

You can also use a LibCST node class name directly (case-insensitive), e.g.:
- `If`, `For`, `Try`, `With`, `Return`, `Assign`, `Call`, ...

### Supported predicate operators

- `=` exact equality
- `!=` not equal
- `~=` substring match
- `^=` prefix match
- `$=` suffix match

Supported attributes (predicates):
- `type`, `kind`, `name`, `qualname`, `start_line`, `end_line`

### XPathFilter Object

The `XPathFilter` class provides a structured way to represent CSTQuery selectors with additional filtering options.

**Location**: `code_analysis/core/database_client/objects/xpath_filter.py`

**Usage**:
```python
from code_analysis.core.database_client.objects.xpath_filter import XPathFilter

# Simple filter
filter_obj = XPathFilter(selector="function[name='my_func']")

# Filter with additional constraints
filter_obj = XPathFilter(
    selector="class[name='MyClass']",
    node_type="class",
    name="MyClass",
    qualname="mypackage.MyClass",
    start_line=10,
    end_line=50
)

# Serialization
data = filter_obj.to_dict()
restored = XPathFilter.from_dict(data)
```

**Attributes**:
- `selector` (required): CSTQuery selector string
- `node_type` (optional): Additional node type filter
- `name` (optional): Additional node name filter
- `qualname` (optional): Additional qualified name filter
- `start_line` (optional): Start line filter
- `end_line` (optional): End line filter

**Methods**:
- `to_dict()`: Convert filter to dictionary for serialization
- `from_dict(data)`: Create filter from dictionary

### Workflow: query → patch

1) Use `query_cst` to find a node and get its `node_id`
2) Use `compose_cst_module` with selector kind `node_id` (or `cst_query`) to replace it
3) Preview diff, then apply

### Performance Considerations

- Typical queries complete in < 100ms for files up to 1000 lines
- Complex queries with multiple predicates may take longer
- Performance tests are available in `tests/performance/test_cst_query_performance.py`
- For large codebases, consider using indexed queries or caching results

### Testing

Comprehensive test coverage (92%+) includes:
- Unit tests for parser (`tests/test_cst_query_parser.py`)
- Unit tests for executor (`tests/test_cst_query_executor.py`)
- Integration tests with real data (`tests/test_cst_query_integration.py`)
- XPathFilter tests (`tests/test_xpath_filter.py`)
- Performance benchmarks (`tests/performance/test_cst_query_performance.py`)
- Special character handling (`tests/test_cst_query_special_chars.py`)


