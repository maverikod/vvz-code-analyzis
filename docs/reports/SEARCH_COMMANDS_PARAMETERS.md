# Search commands — parameter comparison and unification

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document compares parameters of search-related MCP commands and records the decision to use consistent names (e.g. `limit` for maximum number of results).

---

## Commands that limit result count

| Command             | Parameter | Type   | Default | Description                    |
|---------------------|-----------|--------|---------|--------------------------------|
| fulltext_search     | limit     | int    | 20      | Maximum number of results     |
| search_ast_nodes    | limit     | int    | 100     | Maximum results               |
| semantic_search     | **k**     | int    | 10      | Number of results (1–100)    |

**Conclusion:** `fulltext_search` and `search_ast_nodes` use `limit`; `semantic_search` used `k` (FAISS terminology). For consistency and to avoid client errors (e.g. passing `limit` to semantic_search), all search commands should use the same parameter name.

---

## Unification decision: use `limit`

- **Name:** `limit` (same as fulltext_search and search_ast_nodes).
- **Meaning:** Maximum number of results to return.
- **Scope:** Schema (`get_schema`), `execute()` signature, metadata (`metadata()`), and response payload (e.g. `data.limit` instead of `data.k`).
- **Implementation:** In `semantic_search`, accept `limit` in the API and pass it to the FAISS API as `k` internally (e.g. `faiss_manager.search(..., k=limit)`). No change to FAISS or embedding logic.

---

## Other search parameters (no change)

- **project_id** — used by all project-scoped search commands.
- **query** — fulltext_search, semantic_search (search text).
- **entity_type** — fulltext_search only (filter: class | method | function | file).
- **node_type** — search_ast_nodes only (e.g. ClassDef, FunctionDef).
- **file_path** — search_ast_nodes only (optional scope to one file).
- **pattern** — find_classes (SQL LIKE name filter).
- **class_name** — list_class_methods (exact class name).
- **min_score** — semantic_search only (similarity threshold).

---

## After unification

| Command             | Limit parameter | Default |
|---------------------|-----------------|---------|
| fulltext_search     | limit           | 20      |
| search_ast_nodes    | limit           | 100     |
| semantic_search     | limit           | 10      |

Schema, metadata, and code for `semantic_search` are updated so that the only supported parameter for “max results” is `limit`; the response field is also `limit` (replacing `k`).
