## CST tools: compose_cst_module

This project supports CST-based (Concrete Syntax Tree) patching via LibCST to
enable safe refactoring with **logical blocks** while preserving comments.

### MCP command: `compose_cst_module`

**Goal**: replace/insert/remove module-level logical blocks (functions/classes/statements),
normalize imports to the top of the file, then validate the result by compiling it.

### Inputs (high level)

- `root_dir`: project root
- `file_path`: target `.py` file (absolute or relative to `root_dir`)
- `ops`: list of operations
  - `selector`:
    - `kind`: `"function" | "class" | "method" | "range" | "block_id" | "node_id" | "cst_query"`
    - `name`: for `function`/`class`
    - `name`: for `method` use `"ClassName.method"`
    - `start_line`/`end_line`: for `range` selector (module-level statements only)
    - `block_id`: stable id returned by `list_cst_blocks`
    - `node_id`: stable-enough id returned by `query_cst` (span-based)
    - `query`: CSTQuery selector string (when kind=`cst_query`)
    - `match_index`: choose match index when selector returns multiple results (0-based)
  - `new_code`: replacement snippet (empty string means delete)
- `apply`: if true, writes changes to file (only if compile succeeds)
- `create_backup`: if true and apply is true, writes backup into `/.code_mapper_backups/`
- `return_diff`: include unified diff in response
- `return_source`: include full resulting source in response (can be large)

### Output

- `compiled`: `true` if `compile()` succeeded
- `diff`: unified diff (if requested)
- `stats`: `{ replaced, removed, unmatched[] }`
- `backup_path`: path to backup file (when apply=true)

### Notes / limitations

- Operations target **statement blocks** (they can be inside classes/functions too) via `range`.
- Imports inside functions/classes are treated as lazy imports and are not moved.
- Import ordering is preserved as encountered; only moved to the top.

### MCP command: `list_cst_blocks`

Returns "logical blocks" with stable ids and exact line ranges:
- top-level `function` / `class`
- class `method` (qualname `Class.method`)

Typical workflow:
1) `list_cst_blocks` → pick block id
2) `compose_cst_module` with selector kind `block_id` → preview diff + compile
3) repeat
4) `compose_cst_module` with `apply=true`

### MCP command: `query_cst`

Use this command to locate nodes by CSTQuery selectors and get a `node_id` you can
feed into `compose_cst_module`.

See `docs/CST_QUERY.md` for selector rules and examples.


