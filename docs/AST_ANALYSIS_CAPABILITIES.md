# AST Analysis Capabilities - What AST Gives Us

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Executive Summary

AST (Abstract Syntax Tree) is the foundation of our code analysis system. It provides **semantic understanding** of code structure, enabling precise analysis, refactoring, and code intelligence that would be impossible with simple text parsing.

## What AST Provides

### 1. **Semantic Code Understanding** (Not Just Text)

AST transforms code from **text** into **structured data**:

```python
# Text parsing: "def foo(x): return x + 1"
# AST parsing: FunctionDef(name='foo', args=[arg(arg='x')], body=[Return(value=BinOp(...))])
```

**Benefits:**
- Understands code **structure**, not just syntax
- Preserves **relationships** between code elements
- Enables **semantic** operations (not just string manipulation)

### 2. **Precise Code Navigation**

AST provides exact locations and relationships:

- **Line numbers** for every node
- **Parent-child relationships** (class → method → statement)
- **Scope information** (which class a method belongs to)
- **Binding information** (which entity a docstring describes)

**Example from our codebase:**
```python
# code_analysis/core/usage_analyzer.py:130-150
def visit_Call(self, node: ast.Call):
    """Visit function/method call."""
    if isinstance(node.func, ast.Attribute):
        method_name = node.func.attr
        # AST knows: this is obj.method() call
        # AST knows: method_name is 'method'
        # AST knows: obj is node.func.value
```

### 3. **Safe Code Refactoring**

AST enables **semantic refactoring** that preserves code correctness:

**Our refactoring capabilities:**
- **Class splitting** (`ClassSplitter`) - Split large classes while preserving all relationships
- **Superclass extraction** (`SuperclassExtractor`) - Extract common functionality safely
- **Class merging** (`ClassMerger`) - Combine classes with conflict detection

**Why AST is critical:**
- Can **validate** refactoring results (parse modified code)
- Can **preserve** docstrings, comments, type hints
- Can **detect** conflicts (method signatures, inheritance)
- Can **rollback** on errors (syntax validation)

**Example from our codebase:**
```python
# code_analysis/core/refactorer.py:159-237
def split_class(self, config):
    """Split class according to configuration."""
    # 1. Parse AST to understand structure
    tree = ast.parse(file_content)
    class_node = self.find_class(tree, src_class_name)
    
    # 2. Extract members semantically (not text search)
    methods = self.extract_class_members(class_node)
    
    # 3. Build new classes with proper structure
    new_class_code = self._build_new_class(...)
    
    # 4. Validate result (parse again)
    self.validate_python_syntax()
```

### 4. **Dependency Analysis**

AST enables **precise dependency tracking**:

**What we can do:**
- Find **all imports** (import, import from, relative imports)
- Track **usage** of classes, functions, methods
- Build **dependency graphs** (which files depend on which)
- Detect **circular dependencies**
- Find **unused imports**

**Example from our codebase:**
```python
# code_analysis/core/analyzer.py:221-224
elif isinstance(node, ast.Import):
    self._analyze_import(node, file_path, file_id)
elif isinstance(node, ast.ImportFrom):
    self._analyze_import_from(node, file_path, file_id)
```

### 5. **Issue Detection**

AST enables **semantic issue detection**:

**Issues we detect:**
- Missing docstrings (file, class, method level)
- Methods with only `pass` (not abstract)
- `NotImplementedError` in non-abstract methods
- `Any` type usage (type safety issues)
- Generic exception handling
- Invalid imports (cannot be resolved)
- Imports in the middle of files

**Why AST is better than regex:**
- Understands **context** (is this an abstract method?)
- Understands **structure** (is this import at top level?)
- Understands **types** (is this `Any` or `Optional[Any]`?)

**Example from our codebase:**
```python
# code_analysis/core/issue_detector.py:45-88
def _check_any_type_usage(self, node: ast.FunctionDef, ...):
    """Check for Any type usage in function parameters and return type."""
    # Check return type annotation
    if node.returns:
        if isinstance(node.returns, ast.Name) and node.returns.id == "Any":
            # AST knows: this is type annotation, not variable name
            self.issues["any_type_usage"].append(...)
```

### 6. **Code Intelligence**

AST enables **intelligent code search and navigation**:

**Capabilities:**
- **Find usages** - Where is this method called?
- **Find definitions** - Where is this class defined?
- **Class hierarchy** - What classes inherit from this?
- **Method signatures** - What are the parameters?
- **Type information** - What types are used?

**Example from our codebase:**
```python
# code_analysis/core/usage_analyzer.py:105-213
class UsageVisitor(ast.NodeVisitor):
    """AST visitor for finding method calls and attribute accesses."""
    
    def visit_Call(self, node: ast.Call):
        """Visit function/method call."""
        # AST knows: this is a call
        # AST knows: what is being called
        # AST knows: what arguments are passed
        # AST knows: context (which class, which method)
```

### 7. **Vectorization with Context**

AST enables **semantic vectorization** with precise binding:

**What we do:**
- Extract **docstrings** with AST context (which class/method they belong to)
- Extract **comments** with location information
- **Bind chunks** to AST nodes (class_id, method_id, function_id)
- Enable **semantic search** that understands code structure

**Example from our codebase:**
```python
# code_analysis/core/docstring_chunker.py
# AST enables:
# - Extract docstring from ast.get_docstring(node)
# - Know which class/method it belongs to
# - Store with precise binding (class_id, method_id)
# - Enable semantic search: "find classes with methods that do X"
```

## AST vs Text Parsing Comparison

| Feature | Text Parsing | AST Parsing |
|---------|-------------|-------------|
| **Understanding** | Syntax only | Semantic structure |
| **Refactoring** | Risky (string replacement) | Safe (structural changes) |
| **Dependencies** | Regex patterns | Precise import analysis |
| **Issue Detection** | Pattern matching | Context-aware detection |
| **Code Navigation** | Line numbers only | Full relationship graph |
| **Validation** | Cannot validate | Can parse and validate |
| **Type Information** | None | Full type annotations |

## Real-World Examples from Our Codebase

### Example 1: Class Splitting

**Without AST:**
- Would need regex to find class boundaries
- Cannot safely extract methods (might break syntax)
- Cannot validate result
- Cannot preserve docstrings/comments

**With AST:**
```python
# code_analysis/core/refactorer.py
class_node = self.find_class(tree, class_name)  # Precise location
methods = self.extract_class_members(class_node)  # Semantic extraction
new_code = self._build_new_class(...)  # Structural generation
self.validate_python_syntax()  # Can validate!
```

### Example 2: Usage Analysis

**Without AST:**
- Would need regex: `\bmethod_name\(`
- False positives (comments, strings)
- Cannot determine context (which class)

**With AST:**
```python
# code_analysis/core/usage_analyzer.py
def visit_Call(self, node: ast.Call):
    if isinstance(node.func, ast.Attribute):
        method_name = node.func.attr
        # AST knows: this is obj.method() call
        # AST knows: context (self.current_class)
        # AST knows: it's not in a comment or string
```

### Example 3: Issue Detection

**Without AST:**
- Regex: `def.*:\s*pass`
- Cannot distinguish abstract methods
- False positives

**With AST:**
```python
# code_analysis/core/issue_detector.py
def check_method_issues(self, node: ast.FunctionDef, ...):
    # AST knows: is this abstract? (check decorators)
    # AST knows: is body just pass? (check body)
    # AST knows: context (which class, is it abstract?)
```

## AST Commands in Our System

Our MCP commands leverage AST:

1. **`get_ast`** - Retrieve stored AST for a file
2. **`search_ast_nodes`** - Search for specific AST node types
3. **`ast_statistics`** - Get statistics about AST structure
4. **`get_imports`** - Extract all imports (AST-based)
5. **`find_dependencies`** - Build dependency graph (AST-based)
6. **`get_class_hierarchy`** - Get inheritance hierarchy (AST-based)
7. **`find_usages`** - Find where entities are used (AST-based)
8. **`export_graph`** - Export code structure graphs (AST-based)

## Performance Considerations

**AST Parsing:**
- **Fast**: Python's `ast.parse()` is highly optimized
- **Cached**: We store AST in database to avoid re-parsing
- **Incremental**: Only re-parse changed files

**Storage:**
- AST stored as JSON in database
- Can be queried without re-parsing
- Enables fast lookups and analysis

## Conclusion

**AST is not just a parsing tool - it's the foundation for:**

1. ✅ **Semantic code understanding** (not text manipulation)
2. ✅ **Safe refactoring** (with validation and rollback)
3. ✅ **Precise dependency analysis** (exact relationships)
4. ✅ **Intelligent issue detection** (context-aware)
5. ✅ **Code intelligence** (find usages, definitions, hierarchy)
6. ✅ **Semantic vectorization** (chunks bound to code structure)

**Without AST, we would be limited to:**
- ❌ Text search and regex patterns
- ❌ Risky string-based refactoring
- ❌ Inaccurate dependency detection
- ❌ False positives in issue detection
- ❌ No semantic understanding

**AST transforms code analysis from "text processing" to "code understanding".**

