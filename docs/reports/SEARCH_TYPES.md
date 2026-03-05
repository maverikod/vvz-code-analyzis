# Search Types — Overview

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document lists all search-related commands and how they work. Use it to choose the right search for a task.

## Quick reference

| Type              | Command             | Input              | Use case |
|-------------------|---------------------|--------------------|----------|
| Full-text (FTS5)   | `fulltext_search`   | query, project_id  | Find text in code/docstrings |
| Semantic (vectors) | `semantic_search`   | query, project_id, limit | Find conceptually similar code |
| AST by type        | `search_ast_nodes`  | project_id, node_type | Find classes/functions/methods |
| Classes by name    | `find_classes`     | project_id, pattern| List/filter classes (SQL LIKE) |
| Methods of class   | `list_class_methods`| project_id, class_name | List methods of a class |
| Entity lookup     | `get_code_entity_info` | project_id, name, type | Get one entity by name/type |
| List entities     | `list_code_entities`   | project_id, type  | List entities (optionally by type) |
| Usages            | `find_usages`      | project_id, target_name | Where an entity is used |
| Dependencies      | `find_dependencies`| project_id, entity_name | What an entity depends on |
| CST in tree       | `cst_find_node`     | tree_id, query    | Find nodes in loaded CST tree |
| CST in file       | `query_cst`         | project_id, file_path, selector | Find nodes in file by selector |

---

## 1. Full-text search (`fulltext_search`)

- **Source:** `commands/search_mcp_commands.py` → `FulltextSearchMCPCommand`
- **Backend:** SQLite FTS5 table `code_content_fts` (BM25 ranking).
- **Requires:** Index built via `update_indexes` (code mapper fills `code_content` and FTS index).
- **Parameters:** `project_id`, `query`; optional: `entity_type` (class|function|method|file), `limit`.
- **Returns:** `results[]` with `entity_type`, `entity_name`, `content`, `docstring`, `file_path`, `bm25_score`.
- **Docs:** [fulltext_search.md](commands/search/fulltext_search.md).

---

## 2. Semantic search (`semantic_search`)

- **Source:** `commands/semantic_search_mcp.py` → `SemanticSearchMCPCommand`
- **Backend:** Embedding service + FAISS index over code chunks.
- **Requires:** Vector index built (vectorization worker / `revectorize`); embedding service available.
- **Parameters:** `project_id`, `query`; optional `limit` (default 10), `min_score`. Same `limit` as fulltext_search.
- **Returns:** Similar chunks with distance/similarity.
- **Docs:** See command help / COMMANDS_GUIDE.

---

## 3. AST node search (`search_ast_nodes`)

- **Source:** `commands/ast/search_nodes.py` → `SearchASTNodesMCPCommand`
- **Backend:** DB tables `classes`, `functions`, `methods` + `files` (project_id).
- **Requires:** AST/index data from `update_indexes`.
- **Parameters:** `project_id`, optional `node_type` (ClassDef|FunctionDef|class|function|method), `file_path`, `limit`.
- **Returns:** `nodes[]` with `node_type`, `name`, `file_path`, `line`, `docstring` (and `class_name` for methods).
- **Docs:** [docs/commands/ast/](commands/ast/).

---

## 4. Find classes (`find_classes`)

- **Source:** `commands/search_mcp_commands.py` → `FindClassesMCPCommand`
- **Backend:** `database.search_classes(project_id, name=pattern)` (SQL LIKE).
- **Parameters:** `project_id`, optional `pattern` (name filter).
- **Returns:** `classes[]` with class metadata (name, file_path, line, etc.).
- **Docs:** [find_classes.md](commands/search/find_classes.md).

---

## 5. List class methods (`list_class_methods`)

- **Source:** `commands/search_mcp_commands.py` → `ListClassMethodsMCPCommand`
- **Backend:** `SearchCommand.search_methods` → `search_classes(project_id, name)` then `get_class_methods(class_id)` per class; methods returned as dicts via `to_dict()`.
- **Parameters:** `project_id`, `class_name`.
- **Returns:** `methods[]` with method name, signature, file_path, line.
- **Docs:** [list_class_methods.md](commands/search/list_class_methods.md).

---

## 6. Entity info / list entities (AST)

- **get_code_entity_info:** One entity by name/type/path. Source: `commands/ast/entity_info.py`.
- **list_code_entities:** List entities, optional type filter. Source: `commands/ast/list_entities.py`.
- **Backend:** DB entities (classes, functions, methods).
- **Docs:** [docs/commands/ast/](commands/ast/).

---

## 7. Find usages / dependencies (AST)

- **find_usages:** Where `target_name` (and optional type/class) is used. Source: `commands/ast/usages.py`.
- **find_dependencies:** What `entity_name` depends on (usages + imports). Source: `commands/ast/dependencies.py`.
- **Backend:** `usages` table and imports.
- **Docs:** [docs/commands/ast/](commands/ast/).

---

## 8. CST search (in-memory tree vs file)

- **cst_find_node:** Search in an already loaded CST tree (`cst_load_file` → `tree_id`). Simple (type/name/line) or XPath-like `query`. Source: `commands/cst_find_node_command.py`.
- **query_cst:** Search in a file by selector (e.g. `class[name="MyClass"]`) without loading full tree. Source: `commands/query_cst_command.py`.
- **Docs:** [docs/commands/cst/](commands/cst/).

---

## Checking that search works

1. **Index:** Run `update_indexes` for the project so that fulltext, AST, and (if used) vector data are up to date.
2. **Full-text:** Call `fulltext_search` with a word that appears in code or docstrings; expect `results` with `file_path` and `content`.
3. **AST:** Call `search_ast_nodes` with `node_type` `ClassDef` or `FunctionDef`; expect `nodes` with `name`, `file_path`, `line`.
4. **Classes/methods:** Call `find_classes` (optional pattern) and `list_class_methods`(project_id, class_name); expect lists of classes and methods.
5. **Semantic:** Call `semantic_search` only if FAISS and embedding service are configured; expect similar chunks or a clear error.

Unit and integration tests for search commands are in `tests/test_search_commands.py`.
