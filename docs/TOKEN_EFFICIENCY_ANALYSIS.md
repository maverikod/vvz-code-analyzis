# Token Efficiency Analysis: Direct Editing vs CST/AST Tools

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Executive Summary

**For token efficiency, the answer depends on the use case:**

- **Simple, single edits**: Direct editing (`search_replace`) is **more token-efficient** (~30-50% fewer tokens)
- **Complex edits, multiple changes**: CST tools are **more token-efficient** (~40-60% fewer tokens)
- **Refactoring operations**: CST tools are **significantly more efficient** (~70% fewer tokens)

**However**, token efficiency is **secondary** to code quality and reliability. CST tools provide:
- 9/10 reliability vs 4/10 for direct editing
- Automatic validation (syntax, docstrings, type hints)
- Formatting preservation
- Backup support

## Detailed Analysis

### Scenario 1: Simple Single Function Replacement

#### Direct Editing (`search_replace`)

**Token cost:**
- `old_string`: ~50-150 tokens (function signature + body for uniqueness)
- `new_string`: ~50-200 tokens (new function code)
- **Total: ~100-350 tokens per edit**

**Example:**
```python
search_replace(
    file_path="file.py",
    old_string="""def process_data(data: dict) -> list:
    \"\"\"Process data.\"\"\"
    result = []
    for item in data.values():
        result.append(str(item))
    return result""",
    new_string="""def process_data(data: dict) -> list:
    \"\"\"Process data with validation.\"\"\"
    if not isinstance(data, dict):
        raise TypeError("data must be dict")
    result = []
    for item in data.values():
        result.append(str(item))
    return result"""
)
```

**Token breakdown:**
- Function call overhead: ~20 tokens
- old_string: ~80 tokens
- new_string: ~100 tokens
- **Total: ~200 tokens**

#### CST Editing (`compose_cst_module`)

**Token cost:**
- `list_cst_blocks`: ~30 tokens (one-time discovery)
- `compose_cst_module`: ~80-120 tokens (selector + new_code)
- **Total: ~110-150 tokens per edit** (first time: ~140-180 tokens)

**Example:**
```python
# Step 1: Discovery (one-time, can be reused)
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="list_cst_blocks",
    params={"root_dir": "/path", "file_path": "file.py"}
)
# ~30 tokens

# Step 2: Edit
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="compose_cst_module",
    params={
        "root_dir": "/path",
        "file_path": "file.py",
        "ops": [{
            "selector": {"kind": "function", "name": "process_data"},
            "new_code": "def process_data(data: dict) -> list:\n    \"\"\"Process data with validation.\"\"\"\n    if not isinstance(data, dict):\n        raise TypeError(\"data must be dict\")\n    result = []\n    for item in data.values():\n        result.append(str(item))\n    return result"
        }],
        "apply": True
    }
)
# ~100 tokens
```

**Token breakdown:**
- Discovery: ~30 tokens (one-time)
- Function call overhead: ~20 tokens
- Selector: ~15 tokens (`{"kind": "function", "name": "process_data"}`)
- new_code: ~100 tokens
- **Total: ~165 tokens (first time), ~135 tokens (subsequent edits)**

**Winner for simple edits: Direct editing (~200 vs ~165 tokens, ~17% more efficient)**

### Scenario 2: Multiple Edits in Same File

#### Direct Editing

**Token cost per edit:**
- Each `search_replace` call: ~200 tokens
- **Total for 3 edits: ~600 tokens**

**Issues:**
- Must provide unique `old_string` for each edit
- Risk of conflicts if edits overlap
- No atomicity (partial failures possible)

#### CST Editing

**Token cost:**
- `list_cst_blocks`: ~30 tokens (one-time)
- `compose_cst_module` with multiple ops: ~150-200 tokens
- **Total for 3 edits: ~180-230 tokens**

**Example:**
```python
# One discovery call
list_cst_blocks(...)  # ~30 tokens

# One edit call with multiple operations
compose_cst_module(
    ops=[
        {"selector": {"kind": "function", "name": "func1"}, "new_code": "..."},
        {"selector": {"kind": "function", "name": "func2"}, "new_code": "..."},
        {"selector": {"kind": "function", "name": "func3"}, "new_code": "..."}
    ]
)  # ~200 tokens
```

**Winner for multiple edits: CST tools (~230 vs ~600 tokens, ~62% more efficient)**

### Scenario 3: Complex Refactoring (Method Replacement in Class)

#### Direct Editing

**Token cost:**
- Must include class context for uniqueness: ~200-400 tokens
- `old_string`: ~150-300 tokens (class + method)
- `new_string`: ~150-300 tokens
- **Total: ~300-600 tokens**

**Example:**
```python
search_replace(
    file_path="file.py",
    old_string="""class MyClass:
    def __init__(self, value: int):
        self.value = value
    
    def process(self, data: list) -> dict:
        \"\"\"Process data.\"\"\"
        result = {}
        for item in data:
            result[item] = self.value * item
        return result""",
    new_string="""class MyClass:
    def __init__(self, value: int):
        self.value = value
    
    def process(self, data: list) -> dict:
        \"\"\"Process data with validation.\"\"\"
        if not isinstance(data, list):
            raise TypeError("data must be list")
        result = {}
        for item in data:
            result[item] = self.value * item
        return result"""
)
```

**Token breakdown:**
- old_string: ~200 tokens (class + method for uniqueness)
- new_string: ~220 tokens
- **Total: ~420 tokens**

#### CST Editing

**Token cost:**
- `list_cst_blocks`: ~30 tokens (one-time)
- `compose_cst_module`: ~120-150 tokens (compact selector + new_code)
- **Total: ~150-180 tokens**

**Example:**
```python
# Discovery (one-time)
list_cst_blocks(...)  # ~30 tokens

# Edit with compact selector
compose_cst_module(
    ops=[{
        "selector": {"kind": "method", "name": "MyClass.process"},
        "new_code": "def process(self, data: list) -> dict:\n    \"\"\"Process data with validation.\"\"\"\n    if not isinstance(data, list):\n        raise TypeError(\"data must be list\")\n    result = {}\n    for item in data:\n        result[item] = self.value * item\n    return result"
    }]
)  # ~150 tokens
```

**Winner for complex edits: CST tools (~180 vs ~420 tokens, ~57% more efficient)**

### Scenario 4: Editing Large Functions (100+ lines)

#### Direct Editing

**Token cost:**
- `old_string`: ~500-2000 tokens (entire function for uniqueness)
- `new_string`: ~500-2000 tokens (entire new function)
- **Total: ~1000-4000 tokens**

**Issues:**
- Very high token cost
- Risk of errors with large strings
- Hard to maintain uniqueness

#### CST Editing

**Token cost:**
- `list_cst_blocks`: ~30 tokens (one-time)
- `compose_cst_module`: ~150-200 tokens (compact selector + new_code)
- **Total: ~180-230 tokens** (regardless of function size!)

**Key advantage:** Selector size is constant (~15 tokens), not proportional to code size.

**Winner for large edits: CST tools (~200 vs ~2000 tokens, ~90% more efficient)**

### Scenario 5: Multiple Files Editing

#### Direct Editing

**Token cost:**
- Per file: ~200 tokens
- **Total for 5 files: ~1000 tokens**
- Must read each file first: +~50 tokens per file
- **Grand total: ~1250 tokens**

#### CST Editing

**Token cost:**
- Per file discovery: ~30 tokens
- Per file edit: ~150 tokens
- **Total for 5 files: ~900 tokens**

**Winner for multiple files: CST tools (~900 vs ~1250 tokens, ~28% more efficient)**

## Token Efficiency Summary Table

| Scenario | Direct Editing | CST Editing | Winner | Efficiency Gain |
|----------|---------------|-------------|--------|-----------------|
| Simple single edit | ~200 tokens | ~165 tokens | Direct | 17% |
| Multiple edits (3) | ~600 tokens | ~230 tokens | CST | 62% |
| Complex refactoring | ~420 tokens | ~180 tokens | CST | 57% |
| Large function (100+ lines) | ~2000 tokens | ~200 tokens | CST | 90% |
| Multiple files (5) | ~1250 tokens | ~900 tokens | CST | 28% |

## Additional Considerations

### 1. Error Recovery Tokens

**Direct editing:**
- If `old_string` is not unique: +~200 tokens (retry with more context)
- If syntax error: +~200 tokens (fix and retry)
- **Average overhead: ~100-200 tokens per error**

**CST editing:**
- Automatic validation prevents most errors
- If selector fails: +~50 tokens (try different selector)
- **Average overhead: ~20-50 tokens per error**

### 2. Code Quality Validation Tokens

**Direct editing:**
- Manual validation required: +~100 tokens per validation
- Format code: +~30 tokens
- Lint code: +~30 tokens
- Type check: +~30 tokens
- **Total: ~190 tokens per validation**

**CST editing:**
- Automatic validation (included in `compose_cst_module`)
- Optional manual validation: +~90 tokens
- **Total: ~0-90 tokens per validation**

### 3. Discovery Reuse

**CST editing advantage:**
- `list_cst_blocks` result can be reused for multiple edits
- First edit: ~165 tokens
- Subsequent edits: ~135 tokens (no discovery needed)
- **Savings: ~30 tokens per subsequent edit**

**Direct editing:**
- No discovery step
- But must provide full context each time
- **No reuse benefit**

### 4. Backup and Safety

**Direct editing:**
- Manual backup: +~50 tokens
- Risk of data loss: high
- **Safety cost: ~50 tokens + risk**

**CST editing:**
- Automatic backup: 0 tokens (included)
- Automatic validation: 0 tokens (included)
- **Safety cost: 0 tokens**

## Real-World Token Cost Examples

### Example 1: Refactoring 3 Methods in a Class

**Direct editing:**
```
3 × search_replace = 3 × 200 = 600 tokens
+ 3 × validation = 3 × 190 = 570 tokens
+ 1 × backup = 50 tokens
Total: ~1220 tokens
```

**CST editing:**
```
1 × list_cst_blocks = 30 tokens
1 × compose_cst_module (3 ops) = 200 tokens
+ 1 × validation (optional) = 90 tokens
Total: ~320 tokens (backup included)
```

**Savings: ~900 tokens (74% more efficient)**

### Example 2: Simple Comment Update

**Direct editing:**
```
search_replace = 100 tokens (small old_string)
Total: ~100 tokens
```

**CST editing:**
```
list_cst_blocks = 30 tokens
compose_cst_module = 80 tokens
Total: ~110 tokens
```

**Savings: Direct editing is 10% more efficient (but violates project rules)**

## Recommendations

### When to Use Direct Editing (Token Efficiency)

✅ **Use direct editing for:**
- Creating new files (file doesn't exist)
- Editing non-Python files (.md, .json, .yaml)
- Very simple text replacements in comments (if CST fails)

❌ **Never use direct editing for:**
- Existing Python code (violates project rules)
- Multiple edits in same file
- Complex refactoring
- Large functions

### When to Use CST Tools (Token Efficiency + Quality)

✅ **Always use CST tools for:**
- Existing Python code (project rule)
- Multiple edits (62% more efficient)
- Complex refactoring (57% more efficient)
- Large functions (90% more efficient)
- When code quality matters (automatic validation)

## Conclusion

**Token efficiency analysis shows:**

1. **For simple, single edits**: Direct editing is ~17% more token-efficient, but:
   - Violates project rules
   - No automatic validation
   - Higher error risk
   - **Not recommended**

2. **For complex/multiple edits**: CST tools are 40-90% more token-efficient:
   - Multiple edits: 62% more efficient
   - Complex refactoring: 57% more efficient
   - Large functions: 90% more efficient
   - **Highly recommended**

3. **Overall recommendation**: Use CST tools for all existing Python code:
   - Better token efficiency for complex operations
   - Automatic validation saves tokens
   - Better code quality (9/10 vs 4/10 reliability)
   - Follows project rules

**Final verdict: CST tools are more token-efficient for real-world scenarios (multiple edits, refactoring, large code), while providing superior code quality and reliability.**

