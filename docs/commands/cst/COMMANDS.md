# CST Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Per-command schema, parameters, and behavior. Exact schema from each command’s `get_schema()`; metadata from `metadata()`.

---

## cst_load_file — CSTLoadFileCommand

**File:** `commands/cst_load_file_command.py`

**Description:** Load file into CST tree.

**Behavior:** Loads a Python file, parses it to CST, and returns tree (and optionally tree_id for later operations).

---

## cst_save_tree — CSTSaveTreeCommand

**File:** `commands/cst_save_tree_command.py`

**Description:** Save CST tree to file with atomic operations.

**Behavior:** Writes the in-memory CST tree to disk; may update DB file record and backup previous content.

---

## cst_reload_tree — CSTReloadTreeCommand

**File:** `commands/cst_reload_tree_command.py`

**Description:** Reload CST tree from file, updating existing tree in memory.

**Behavior:** Re-reads file from disk and rebuilds CST tree, replacing current in-memory tree.

---

## cst_find_node — CSTFindNodeCommand

**File:** `commands/cst_find_node_command.py`

**Description:** Find nodes in CST tree.

**Behavior:** Accepts tree_id (or file) and selector/criteria; returns matching node IDs or node data.

---

## cst_get_node_info — CSTGetNodeInfoCommand

**File:** `commands/cst_get_node_info_command.py`

**Description:** Get detailed information about a node.

**Behavior:** Accepts tree_id and node_id; returns node type, span, code slice, children, etc.

---

## cst_get_node_by_range — CSTGetNodeByRangeCommand

**File:** `commands/cst_get_node_by_range_command.py`

**Description:** Get node ID for a specific line range.

**Behavior:** Accepts tree_id and line range (start_line, end_line); returns node that spans that range (or best match).

---

## cst_modify_tree — CSTModifyTreeCommand

**File:** `commands/cst_modify_tree_command.py`

**Description:** Modify CST tree with atomic operations.

**Behavior:** Accepts tree_id and list of operations (insert/replace/remove); applies them and returns updated tree or success.

---

## compose_cst_module — ComposeCSTModuleCommand

**File:** `commands/cst_compose_module_command.py`

**Description:** Compose/patch a module using CST tree. Attaches a branch (tree_id) to a node in a file or overwrites/creates a file.

**Process (summary):** (1) Check project exists. (2) Get CST tree (branch) from tree_id. (3) If node_id given → load file, find node, insert branch. (4) If node_id empty → overwrite file with branch (or create). (5) Write temp file, validate (compile, flake8, mypy, docstrings). (6) Backup DB file data if exists, transaction: clear old file data, apply new data, replace file, commit. (7) Optional Git commit. (8) On error: rollback and restore backup.

**Validations:** Project, node (if node_id), non-empty branch, compilation, Flake8, mypy, docstrings.

---

## cst_create_file — CSTCreateFileCommand

**File:** `commands/cst_create_file_command.py`

**Description:** Create a new Python file with docstring.

**Behavior:** Creates a new file under project root with given path and docstring (and optionally initial content).

---

## cst_convert_and_save — CSTConvertAndSaveCommand

**File:** `commands/cst_convert_and_save_command.py`

**Description:** Convert source code to CST, save CST and AST to database.

**Behavior:** Parses given source (or file path) to CST, stores CST and derived AST in DB, returns tree_id and file metadata.

---

## list_cst_blocks — ListCSTBlocksCommand

**File:** `commands/list_cst_blocks_command.py`

**Description:** List CST blocks (e.g. top-level nodes) for a file or tree.

**Behavior:** Returns list of block-level nodes (modules, classes, functions) with ids and spans.

---

## query_cst — QueryCSTCommand

**File:** `commands/query_cst_command.py`

**Description:** Run CST query (selector language) on a tree.

**Behavior:** Accepts tree_id and query (e.g. selector steps); returns matching nodes or values.
