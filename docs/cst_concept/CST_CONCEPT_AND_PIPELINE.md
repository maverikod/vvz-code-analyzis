# CST: Concept and Code-Editing Pipeline

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Purpose

This document describes the **concept** and **end-to-end pipeline** for working with Python code via the CST (Concrete Syntax Tree) server commands instead of direct file read/write. It is the single reference for: what the CST workflow is, how loading by levels and node expansion work, how to “write a node” (parent + file), how files with syntax errors are handled, and how this compares to direct text editing.

---

## 1. Core Concepts

### 1.1 Tree, node, parent, file

- **Tree** — in-memory representation of one Python file (LibCST module). Identified by `tree_id` after load.
- **Node** — an element of the tree: module, class, function, statement, expression, etc. Identified by `node_id`. Has type (e.g. `FunctionDef`), kind (e.g. `function`, `method`), name/qualname, and position (start/end line/col).
- **Parent** — the containing node (e.g. the class that contains a method). The root of the tree is the **Module** node; it has no parent. The reserved sentinel **`__root__`** denotes the module root when specifying where to insert (exact spelling in code: `ROOT_NODE_ID_SENTINEL = "__root__"`).
- **File** — the target path (relative to project root) where the tree is loaded from and saved to. One tree ↔ one file at a time.

### 1.2 Working with a node, then writing it

- You **work with a node**: load the file (or only its structure), then request that node — with only direct children or with the full subtree (recursive).
- You **write a node** by giving a command that specifies:
  - **Parent** (or root sentinel) — where the node belongs (e.g. a class node_id, or `__root__` for module level),
  - **File** — `project_id` and `file_path` where the tree is (or will be) saved.

So: “get node” (optionally with children direct/recursive) → “write node” (parent + file). The pipeline is node-centric: you view and load only what you need, then you insert/replace at a parent in a given file.

### 1.3 Loading by levels (skeleton = collapsed branches; expand on demand)

- **Structure-only load (skeleton)** — The model sees what a modern editor shows with **collapsed branches**: full structure, no implementation bodies. Concretely:
  - **Module level:** file docstring, module-level variables, module-level expressions — **full** (full text).
  - **Classes/functions/methods:** for each callable, the skeleton shows the **full signature** (including full parameter list), **docstring**, and a **body placeholder** — the body is replaced by a single comment and `pass`, e.g.:
    ```python
    def fun(self, full_param_list):
        """Docstring of the method."""
        # Call node body to see code
        pass
    ```
  So the response is full code but with **all method/function bodies** collapsed to docstring + comment + `pass`. No algorithm implementation in the skeleton.
- **Selector in the same request** — Together with the file read (load) request, the client can pass an optional **selector**. The selector can be, among other things, a **list of node identifiers** (e.g. `node_ids`). The server then returns the skeleton (or structure) **and** the content of the nodes matching the selector (e.g. full body for those node_ids) in one response. So one call can be: load file + "expand these nodes" via selector (e.g. list of identifiers).
- **Expand on demand (separate call)** — Alternatively, the model can request node(s) in a separate call (e.g. `cst_get_node_info` with `include_code=True`, or a batch variant). Expansion scope: **direct children only** or **recursive** (full subtree).

The tree on the server is built from the full file (full parse). The skeleton and optional selector affect only **what is returned** in the load response. This keeps context small: structure first (collapsed), optionally with selected nodes in the same request, or load nodes in a follow-up call.

---

## 2. Pipeline: End-to-End Workflow

### 2.1 Load file

- **cst_load_file**(project_id, file_path; optional **selector**)  
  - Parses the file, builds the tree, returns `tree_id` and node metadata (or skeleton: only structure). Optionally accepts a **selector** (e.g. a list of node identifiers); the response then includes the structure **and** the content of the nodes matching the selector in the same call.
  - If the file has syntax errors, see **Section 4**.

### 2.2 Discover and inspect nodes

- **cst_find_node**(tree_id, search_type, query) — find nodes by simple or XPath-like query.
- **cst_get_node_by_range**(tree_id, start_line, end_line) — get node(s) covering a line range.
- **cst_get_node_info**(tree_id, node_id; include_code, include_children, include_parent; **children_scope**: direct | recursive)  
  - Get one node; optionally with code, parent, and children.  
  - **direct** = only immediate children; **recursive** = full subtree.  
  - This is the “expand node” step when you loaded structure first.

### 2.3 Modify tree

- **cst_modify_tree**(tree_id, operations)  
  - Operations: **replace** (node_id + new code), **insert** (parent_node_id or **`__root__`** + code + **position**: `first` | `last` | after sibling index N), **delete** (node_id), **move** (node_id + new parent + position).  
  - Use **code_lines** (array of strings) for multi-line code to avoid JSON escaping.  
  - All operations in one call are validated and applied atomically; on failure the tree is rolled back.

### 2.4 Save to file

- **cst_save_tree**(tree_id, project_id, file_path; backup, validate, commit_message)  
  - Writes the tree to the file atomically (with backup and optional git commit).  
  - This is “write the node (and the rest of the tree)” to the given file: you specify the **file** (project_id + file_path); the parent/position was already used at modify time.

### 2.5 Create new file

- **cst_create_file**(project_id, file_path, docstring) — creates a new .py file with only the docstring, returns `tree_id`.  
- Then use **cst_modify_tree** to insert code (e.g. at module root or under a class) and **cst_save_tree** to persist.

### 2.6 Alternative: file-based single edit (no tree)

- **query_cst**(project_id, file_path, selector; replace_with or code_lines; match_index, replace_all) — find by selector and replace in one call; file is written and DB updated. No tree in memory. No “write node by parent” here; useful for one-off find-and-replace.

---

## 3. Writing a Node: Parent and File

Conceptually:

- **Modify** step: you already specified the **parent** (or target node and position) when you did **insert** or **replace** in `cst_modify_tree`. So the “where in the tree” is defined by parent_node_id / target_node_id / node_id.
- **Save** step: you specify the **file** — `project_id` and `file_path`. That is where the entire tree (including the node you changed) is written.

So “write a node” = do the insert/replace (which implies parent/target) + then save the tree to the given file. No separate “write node(parent, file)” command is required; the existing **cst_modify_tree** + **cst_save_tree** pipeline already express “parent (or root) + file.”

---

## 4. Files with Syntax Errors

### 4.1 Goal

Allow the model to work with a file that does not parse: get a valid tree, see which lines were “error” lines, fix them in the tree, and save.

### 4.2 Behavior (concept)

- On **cst_load_file**, if the parser reports a syntax error:
  1. The tool **comments out** the reported line (and adds a clear marker so the model understands it was commented due to an error).
  2. If the line is a block starter (if/def/class/for/…), it inserts a **pass** so that empty blocks do not cause “empty body” errors.
  3. It parses again. If there is still an error, it comments out another line (and adds pass if needed). This repeats until the file parses.
  4. The result is a **valid tree** where the formerly erroneous code is represented as **comment nodes** (and optional `pass` nodes). Nothing new is added to the response contract: the tool already returns **nodes/lines where the error was detected** (e.g. `commented_lines`: line, error, parent_node).

### 4.3 Node type change: code → comment

- Conceptually, the only change is the **type** of the node: it **was** code (a statement/expression), it **became** a comment (same content, commented out), possibly followed by `pass`. The response already points to those nodes/lines.
- The model sees a valid tree and the list of commented (error) locations. To fix: **replace** those comment (+ pass) nodes with the correct code via **cst_modify_tree**, then **cst_save_tree**. So the node “type” changes back: comment → code.

### 4.4 Summary

- Iterative comment-out until parse succeeds; error lines become comments (+ pass where needed).
- Response already carries the nodes/lines where the error was found.
- Model fixes by replacing comment (and pass) with real code and saves. No change to the response shape; only the tree representation of the bad line changes from code to comment.

---

## 5. Comparison: CST Pipeline vs Direct Text Editing

### 5.1 Advantages of CST

- **Syntax and structure** — Edits are applied to a parsed tree; the server can validate that the result compiles. No accidental broken syntax from raw string replacement.
- **Atomicity and safety** — Modify validates all operations; on failure the tree is unchanged. Save is atomic with backup and optional rollback.
- **Context control** — Load structure only, then expand only the node you need (direct or recursive). Less token usage than sending the whole file.
- **Semantic operations** — Insert/replace/delete by node (e.g. “replace this function”) instead of by line range; formatting and comments can be preserved by the tree.
- **Single source of truth** — One tree per file on the server; no drift between “what the model thinks” and “what the file is” until an explicit save.
- **Error recovery** — Files with syntax errors can still be loaded (error lines → comments + pass); model can fix in tree and save.

### 5.2 Disadvantages of CST

- **Round-trips** — Load → get node → modify → save is several calls; direct edit is one read + one write.
- **Depends on server** — No CST workflow when the server is down; direct tools still work (with user approval for fallback).
- **Learning curve** — Need tree_id, node_id, parent; selectors or range for discovery.
- **Not all edits need structure** — Simple find-and-replace may be easier with **query_cst** replace or even raw text in non-Python or when server is unavailable (with approval).

### 5.3 Why CST is not slower in practice (reading and writing)

- **Reading:** With direct edit you must either grep many times or read the whole file to avoid breaking code; with CST you get the skeleton once and see structure in compact form (1.1 vs 1.2).
- **Writing:** A text diff often causes IndentationError and similar, leading to extra reads and analysis; with CST you insert a node and the tool blocks invalid write (2.1 vs 2.2).
- **Replace:** Replacing by node_id (and parent_id for insert) forces you to resolve the node and parent explicitly — i.e. to read the code consciously. With direct edit it is easy to “assume” and break code without a clear picture of structure (3.1).

So in practice CST does not lose on speed (comparable or fewer effective reads), and wins on safety and conscious editing.

### 5.4 When to use which

- **Prefer CST** for: Python code in projects managed by the server; multi-step edits; refactors; when you want validation, backup, and structure-aware edits; when you want to limit context (structure + one node).
- **Use direct edit only** when: server is unavailable and user approved fallback; or non-Python files; or one-off scripts outside the project. For Python in test_data or server-managed projects, use CST only.

---

## 6. Strategy: Working with Code on CST Nodes

This section defines the **default strategy** for reading and writing code via CST: skeleton-first, configurable node expansion, and write as “set of nodes + file”.

### 6.1 Reading: default is skeleton (collapsed branches)

- **By default**, load returns the **skeleton** = what a modern editor shows with collapsed branches: full structure without implementation bodies. Module-level: file docstring, variables, expressions — full. Each function/method: **full signature**, **docstring**, body replaced by a comment and `pass` (see §1.3). So the model sees complete structure but no algorithm code.
- **Optional selector in the load request:** Together with the read (load) request, the client can pass a **selector** that can correspond to a **list of node identifiers** (or other selector types). The response then includes the structure (skeleton or full) **and** the content of the nodes matching the selector (e.g. full body for those node_ids) in one call. So "load file + expand these nodes" is a single request when a selector (e.g. list of identifiers) is provided.
- Alternatively, real body content can be requested in a separate call (single node or multiple nodes by list of `node_id`s); the server must support at least one of: selector in load, or a separate multi-node request.

### 6.2 Node request modes

A request for a node (or nodes) can work in different modes:

| Mode | Description | Use case |
|------|-------------|----------|
| **Direct children only** | Only immediate children of the node. | Inspect method/block structure (what statements it contains) without full bodies. |
| **Descendants up to N levels** | Children + grandchildren + … up to depth N. | Bounded expansion when full subtree is too large. |
| **Whole branch** | Full subtree (all descendants). | Need complete content of a class/function for edit or analysis. |
| **Branches by selector** | Find nodes by selector (e.g. CSTQuery); return those nodes (each with chosen depth: direct / N levels / full). | “All methods named `run`”, “all classes in this file”, then expand only matches. |

Because **node IDs are UUID4** and stable within the tree, **multiple replacement by selector** is supported: find nodes by selector → obtain their `node_id`s → pass several **replace** operations in one **cst_modify_tree** call (same tree_id, multiple operations). The batch is validated and applied atomically.

### 6.3 Write: set of nodes + file; precise positioning; insert vs replace vs move

- **Write** = pass a **set of nodes** and the **file** (project_id + file_path). The server applies the corresponding modify operations and saves the tree to that file.
- **Positioning:** Every insert/move must be precisely positioned:
  - **Parent:** `parent_node_id` (the node under which to place the child), or the sentinel **`__root__`** for module level. If not specified, `__root__` is assumed.
  - **Position within parent:** `first` = as first child; `last` = as last child; or **after index N** (0-based index of a sibling; if N is out of range, treat as "last").
- **Insert vs move** is determined by the tool: if a node with the given `node_id` **already exists** in the tree -> **move** (change parent/position, keep content); if it does **not** exist -> **insert** (add new node with given code).
- **Write semantics (replace/upsert):**
  - If the node with that `node_id` **exists** and is already at the right parent and position -> **replace** its content (and descendants) with the new code.
  - If the node **does not exist** -> **insert** at the given parent and position.
  - If the node **exists but** parent or position is different -> **remove** the node from its current place and **insert** it at the new parent/position with the new content (move + replace in one).

So the write contract is: **nodes + file**; **parent** (or `__root__`) and **position** (first | last | after N) for insert/move; the tool infers replace vs insert vs move from presence of `node_id` in the tree and target parent/position.

### 6.3a Batch as operation language (node + action)

This refines the write path described in §6.3 by expressing it as a single batch of (node + action). To cut down on round-trips, the client sends **one batch** in which each item is not just a node but **node + what to do with it**. The batch is like a small **operation language**:

| Action | Meaning | Parameters (besides node_id) |
|--------|--------|-------------------------------|
| **delete** | Remove the node from the tree. | — |
| **move** | Keep the node content, change its parent and position. | `parent_node_id` or `__root__`; `position`: `first` | `last` | `after` + sibling index N (0-based; if N out of range, last). |
| **replace** | Keep the node’s place, change its content (and descendants). | `code` or `code_lines` (new code). |

- One request = list of `(node_id, action, ...params)`. The server validates the whole batch and applies it atomically (all or nothing).
- **New nodes** (insert) use action **insert** with `parent_node_id` (or `__root__`), `position` (`first` | `last` | after index N), and `code` / `code_lines`.
- **Insert vs move:** if `node_id` exists in the tree -> move; if not -> insert. Same for write/upsert: existing node at same place -> replace; existing at different place -> remove + insert; no node -> insert.
- Batch vocabulary: **delete**, **move**, **replace**, **insert**. Optionally the same batch can be passed with **file** (project_id, file_path) for apply + save in one round-trip.

### 6.4 Error handling and tree lifecycle

- **Modify fails** — Operations are validated before apply; if any operation is invalid (bad node_id, invalid code), none are applied and the tree is unchanged. Use **preview** (e.g. `cst_modify_tree` with `preview=true` where supported) to see the diff without applying, then apply and save.
- **Save fails** — If save fails (e.g. validation of generated code, write error), **nothing must change**: file on disk unchanged, database unchanged. The tool must return a **clear error description** for the model. When apply+save is in one request: on save failure the in-memory tree must be **rolled back** to the state before the batch, so that no partial state persists and the model can retry the same request after fixing the cause.
- **Tree staleness** — The tree is a snapshot. If the file was changed on disk (by another process or tool), reload before modifying: **cst_reload_tree**(tree_id) to refresh from file, or load again to get a new tree_id.
- **Lifecycle** — Tree lives in server memory until the process ends or the tree is explicitly removed. After **cst_save_tree**, the file on disk matches the tree; use **auto_reload** (if supported) to keep tree_id valid after save.

### 6.5 Multi-file edits

- One tree = one file. To change several files: for each file, **load** → modify → **save** (and optionally reload or load the next file). There is no atomic transaction across files; order matters if files depend on each other (e.g. fix module A, then B that imports A).

### 6.6 Choosing how to find a node

| Need | Command / approach |
|------|--------------------|
| By name / type (e.g. “function named `run`”, “all classes”) | **cst_find_node**(tree_id, search_type, query) or **query_cst**(project_id, file_path, selector) if you have no tree yet. |
| By line range (e.g. “node covering lines 45–50”) | **cst_get_node_by_range**(tree_id, start_line, end_line). |
| By selector in a file without loading full tree | **query_cst**(project_id, file_path, selector); then for deeper work load the file and use node_id from matches. |
| Node + parent in one call (convenience) | **cst_get_node_at_line**(tree_id, line) returns node and parent in one response. |

### 6.7 Possible extensions (from gap analysis)

- **get_file_lines**(project_id, file_path, start_line, end_line) — **Implemented.** Return raw lines without parsing; for “show lines around error” when the file does not parse at all.
- **Skeleton as default** — **Implemented.** **cst_load_file** has **return_format**: `"full"` (default) | `"skeleton"`; with `"skeleton"` the response is structure-only (signatures, docstrings, body = comment + pass for callables).
- **Node + parent in one call** — **Implemented:** **cst_get_node_at_line**(tree_id, line) returns the node spanning that line and its parent in one response, reducing round-trips.
- **Selector in load request** — **Implemented.** **cst_load_file** accepts an optional **selector** (XPath-like string or list of node_ids); the response includes structure (full or skeleton) and **selected_nodes** with content for the matching nodes in one call.

---

## 7. Summary

- **Concept**: Work with **nodes** (load structure, expand node with direct or recursive children), then **write** by specifying **parent** (at modify time) and **file** (at save time). Node-centric pipeline.
- **Strategy**: Read by default = top-level skeleton only. Node request = direct children / N levels / whole branch / by selector. Multiple replace by selector is supported (UUID4 node_ids → batch replace in one call). Write = set of nodes + file; new nodes require parent (includes move = same node, new parent). **Batch as operation language**: one request = list of (node_id, action) with action in { delete, move, replace, insert }; fewer round-trips, atomic apply.
- **Pipeline**: Load (skeleton or full) → find/get node (chosen mode) → modify (replace/insert/delete) → save (file). Create file with **cst_create_file** then modify + save.
- **Syntax errors**: Tool comments out error lines (and adds pass where needed) until parse succeeds; those places are already reported; in the tree they are comment nodes. Model replaces comment→code and saves.
- **vs direct editing**: CST gives structure, validation, atomicity, and context control; use CST for Python in managed projects; reserve direct edit for fallback or non-Python.

---

## 8. Comparative analysis: CST vs direct editing and writing

This section compares the CST pipeline with **direct editing and writing** (read_file, grep, search_replace, write on the same codebase) across the main dimensions implied by the document. “Direct” = file/editor tools without a CST server.

### 8.1 Reading and understanding code

| Aspect | CST | Direct |
|--------|-----|--------|
| **First view** | Skeleton only (default): docstring, classes, functions, variables, methods with ids and line ranges. Compact. | Whole file or many grep/read_file calls to avoid blind edits. |
| **Deep dive** | Request one node with chosen scope: direct children, N levels, or full branch. By selector possible. | Read full file or repeated grep; no “node” boundary, risk of wrong context. |
| **Locating** | By node_id, selector, or line range; parent/children explicit. | By line numbers or text search; structure implicit, easy to mis-target. |
| **Token/context** | Only what you request (skeleton + one branch). | Often whole file or many fragments to be safe. |

**Conclusion:** CST gives a structured, compact first view and targeted expansion; direct editing typically needs the whole file or many reads to avoid breaking code.

### 8.2 Writing: insert, replace, delete, move

| Aspect | CST | Direct |
|--------|-----|--------|
| **Insert** | By parent (or target) + position; server validates syntax and structure. | Patch/diff by line; high risk of IndentationError, mixed tabs/spaces, wrong block. |
| **Replace** | By node_id + new code; atomic, validated. | search_replace by string/pattern; can hit wrong occurrence or break structure. |
| **Delete** | By node_id; subtree removed cleanly. | Delete lines or pattern; can leave broken blocks or half-statements. |
| **Move** | First-class or delete+insert: node_id + new parent + position. | Copy lines + delete + insert; indentation and context errors frequent. |
| **Validation** | Before apply: invalid ops rejected, tree unchanged. | None; broken file only discovered on next run/lint. |

**Conclusion:** CST treats insert/replace/delete/move as semantic operations on nodes with validation; direct editing is text-based and error-prone (indentation, scope, duplicates).

### 8.3 Batching and round-trips

| Aspect | CST | Direct |
|--------|-----|--------|
| **Batch** | One request = list of (node_id, action): delete, move, replace, insert. Atomic apply. Optional: same request includes file → apply + save in one round-trip. | Each change = separate search_replace or edit; no atomic batch. |
| **Round-trips** | Load (skeleton) → get node(s) → batch modify (+ save). With batch apply+save: fewer calls. | Many read_file/grep to understand, then one or many write/search_replace. |
| **Intent** | Explicit operation language (action per node). | Implicit (text diff); intent only in model’s head. |

**Conclusion:** CST supports a clear operation language and atomic batch (node + action, optional apply+save); direct editing has no batch abstraction and no atomic multi-change.

### 8.4 Syntax and structure safety

| Aspect | CST | Direct |
|--------|-----|--------|
| **Before write** | Parsed tree; operations checked (node exists, code compiles). | No check; invalid Python possible. |
| **After write** | Save can validate (compile); backup + rollback on failure. | File written as-is; errors found later. |
| **Structure** | Node boundaries and parent/child preserved; no “half node”. | Easy to cut mid-statement or corrupt blocks. |

**Conclusion:** CST enforces syntax and structure at modify and optionally at save; direct editing has no structural guarantee.

### 8.5 Files with syntax errors

| Aspect | CST | Direct |
|--------|-----|--------|
| **Load** | Iterative comment-out + pass until parse succeeds; tree with comment nodes; response lists error locations. | read_file returns raw text; no structure; model must guess error location. |
| **Fix** | Replace comment (+ pass) nodes with correct code in tree, then save. | Edit text; risk of new errors or wrong line. |
| **Discovery** | commented_lines (line, error, parent_node) in response. | Manual inspection of raw lines. |

**Conclusion:** CST allows loading broken files as a valid tree (error → comment) and fixing by node; direct editing has no structured error representation.

### 8.6 Multi-file edits

| Aspect | CST | Direct |
|--------|-----|--------|
| **Scope** | One tree = one file; multi-file = sequence load→modify→save per file. | Can edit several files with multiple read/write per file. |
| **Atomicity** | No cross-file transaction; order of files matters. | No cross-file transaction either. |
| **Consistency** | Per-file backup and validation. | No automatic backup; consistency by discipline. |

**Conclusion:** Both are per-file; CST gives per-file backup and validation, direct does not.

### 8.7 Error recovery and lifecycle

| Aspect | CST | Direct |
|--------|-----|--------|
| **Modify failure** | Whole batch rejected; tree unchanged; preview possible. | Partial write may leave file broken. |
| **Save failure** | Rollback from backup; file unchanged. | File may be half-written. |
| **Staleness** | Tree = snapshot; reload when file changed elsewhere. | read_file always sees current file; no “tree” to stale. |
| **Backup** | Mandatory backup before save (configurable). | None unless done manually. |

**Conclusion:** CST offers predictable failure (no partial apply), backup, and rollback; direct editing does not.

### 8.8 Context and conscious editing

| Aspect | CST | Direct |
|--------|-----|--------|
| **Targeting** | Must resolve node_id (and parent for insert) → forces explicit “where”. | Can edit by line or pattern without understanding structure → “assumptions” that break code. |
| **Context size** | Skeleton + selected node(s) only. | Often whole file or many fragments. |

**Conclusion:** CST encourages conscious targeting (node + parent); direct editing allows blind edits by line/pattern.

### 8.9 Dependencies and applicability

| Aspect | CST | Direct |
|--------|-----|--------|
| **Server** | Requires CST server (e.g. code-analysis-server). | Only file/editor tools. |
| **Language** | Python (and what the CST supports). | Any text; no structure. |
| **Fallback** | When server down: direct edit only with user approval. | Always available. |

**Conclusion:** CST is better when the server is available and the code is Python in a managed project; direct is the fallback and for non-Python or ad-hoc scripts.

### 8.10 Summary table (CST vs direct)

| Dimension | CST | Direct |
|-----------|-----|--------|
| Reading | Skeleton + on-demand node (direct / N levels / full / selector). | Whole file or many grep/reads. |
| Writing | Node + action (delete, move, replace, insert); validated; atomic batch. | Text diff; no structure; no batch. |
| Safety | Syntax/structure validated; backup; rollback. | None. |
| Broken files | Load as tree (error→comment); fix by node. | Raw text only. |
| Round-trips | Reduced by batch and optional apply+save. | Many reads to be safe; N writes for N edits. |
| Conscious edit | node_id + parent force explicit targeting. | Easy to edit without structure. |

**Overall:** CST is superior for structured reading, safe and batched writing, and handling syntax errors, at the cost of depending on the server and learning node/selector concepts. Direct editing remains necessary as fallback and for non-Python or unmanaged files.

---

## 9. Conclusion (итог)

*(This section is in Russian as a summary for the team.)*

- **Подход:** Редактирование кода через **узлы CST**: загрузка скелета → точечная подгрузка узла (прямые потомки / N уровней / ветка / по селектору) → батч операций (удалить, перенести, заменить, вставить) + файл → атомарное применение и сохранение.
- **Чтение:** По умолчанию — только каркас; контекст грузится по запросу. Меньше токенов, осознанный выбор узла и родителя.
- **Запись:** Язык операций: (node_id, action). Валидация до применения; при ошибке дерево не меняется; бэкап и откат при сохранении.
- **Сломанный файл:** Ошибочные строки превращаются в комментарии (+ pass); дерево валидно; модель правит узлы и сохраняет.
- **Против прямого редактирования:** CST выигрывает по структуре, безопасности, батчингу и работе с ошибками; прямое редактирование — только fallback и для не-Python.
- **Итог:** Стратегия работы с кодом — на узлах CST: скелет, узел по необходимости, батч (node + action) + файл, один раунд apply+save. Для Python в управляемых проектах — CST по умолчанию.

---

## 10. Effectiveness of methods

Evaluation of pipeline methods by impact on **context size**, **round-trips**, **safety**, and **clarity**. Higher effectiveness = stronger contribution to the strategy (replace direct editing, limit context, safe writes).

| Method | Effectiveness | Notes |
|--------|---------------|--------|
| **Skeleton load (default)** | **High** | One response = compact structure; avoids sending full file. Critical for token economy and “see before expand”. |
| **Get node: direct children** | **High** | Inspect method/block structure without full bodies; keeps context small. |
| **Get node: N levels** | **Medium–High** | Bounded expansion when full subtree is too large; tunable. |
| **Get node: full branch** | **Medium** | Full content when needed; can be large — use only when necessary. |
| **Get node: by selector** | **High** | Find then expand only matches (e.g. all `run` methods); avoids scanning whole tree in client. |
| **cst_find_node** | **High** | Locate by query without loading full node list; pairs well with skeleton. |
| **cst_get_node_by_range** | **High** | When you know line range (e.g. from linter); single call to get node_id. |
| **cst_get_node_info** (with scope) | **High** | Single place for “expand node” with direct/recursive choice; reduces guesswork. |
| **cst_modify_tree** (replace/insert/delete) | **High** | Atomic, validated; core of safe write. Batch of ops = one round-trip. |
| **Batch: node + action** (delete, move, replace, insert) | **High** | Cuts round-trips; explicit intent; one apply (+ optional save). |
| **cst_save_tree** (backup, validate) | **High** | Atomic write + rollback; essential for safety. |
| **Preview before apply** | **Medium** | Reduces failed apply; extra round-trip for preview. |
| **Syntax-error load** (comment + pass) | **High** | Only way to get a tree from broken file; enables fix-by-node. |
| **query_cst** (no tree, find+replace) | **Medium** | One call for simple replace; no structure for multi-step or move. |
| **cst_create_file** | **Medium** | Creates file + tree; then modify+save for body. Fills gap “new file”. |

**Summary:**
- **Highest impact:** skeleton load, get-node by scope/selector, batch (node + action), modify_tree, save_tree with backup, syntax-error handling. These directly reduce context, round-trips, and risk.
- **Supporting:** find_node, get_node_by_range, get_node_info with children_scope — enable targeted discovery without full dump.
- **Lower impact but needed:** query_cst for one-off replace; create_file for new files; preview for cautious apply.
