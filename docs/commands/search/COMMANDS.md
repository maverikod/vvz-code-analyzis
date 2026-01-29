# Search Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

All in `commands/search_mcp_commands.py`. Internal: `SearchCommand` in `commands/search.py`. Schema from `get_schema()`; metadata from `metadata()`.

---

## fulltext_search — FulltextSearchMCPCommand

**Description:** Full-text search over project (e.g. file contents, docstrings, or DB full-text index).

**Behavior:** Accepts query string and optional scope (project/file); returns matching files and snippets.

---

## list_class_methods — ListClassMethodsMCPCommand

**Description:** List methods of a class (optionally with signatures and docstrings).

**Behavior:** Accepts project/file and class name; returns list of methods from entities DB or AST.

---

## find_classes — FindClassesMCPCommand

**Description:** Find classes by name or pattern in project or file.

**Behavior:** Returns list of classes matching the given name or pattern with location and metadata.
