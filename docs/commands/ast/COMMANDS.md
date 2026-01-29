# AST Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Per-command schema, parameters, and behavior. Exact schema comes from each command’s `get_schema()`; metadata from `metadata()`.

---

## get_ast — GetASTMCPCommand

**File:** `commands/ast/get_ast.py`

**Description:** Retrieve stored AST for a given file.

**Schema (main):** `root_dir` (required), `file_path` (required), `include_json` (boolean, default true), `project_id` (optional). Path can be absolute or relative to project root.

**Behavior:** Resolves project by root_dir/project_id, finds file by path (exact, then versioned path, then by filename), loads AST from DB and returns it; optionally includes full AST JSON.

---

## search_ast_nodes — SearchASTNodesMCPCommand

**File:** `commands/ast/search_nodes.py`

**Description:** Search AST nodes across project/files.

**Behavior:** Accepts project scope (root_dir, optional project_id) and search criteria; queries AST nodes and returns matching nodes (e.g. by type, name, or XPath-style filter).

---

## ast_statistics — ASTStatisticsMCPCommand

**File:** `commands/ast/statistics.py`

**Description:** Get AST statistics for project or a specific file.

**Behavior:** Returns counts/summary (e.g. nodes by type, files with AST) for the given project or file.

---

## list_project_files — ListProjectFilesMCPCommand

**File:** `commands/ast/list_files.py`

**Description:** List all files in a project with metadata.

**Behavior:** Returns list of files in the project (path, id, metadata) from the database.

---

## get_code_entity_info — GetCodeEntityInfoMCPCommand

**File:** `commands/ast/entity_info.py`

**Description:** Get detailed information about a code entity (class, function, method).

**Behavior:** Accepts project/file and entity identifier; returns entity details (name, type, location, docstring, etc.) from AST/entities DB.

---

## list_code_entities — ListCodeEntitiesMCPCommand

**File:** `commands/ast/list_entities.py`

**Description:** List code entities (classes, functions, methods) in a file or project.

**Behavior:** Returns list of entities for the given file or project (optionally filtered by type).

---

## get_imports — GetImportsMCPCommand

**File:** `commands/ast/imports.py`

**Description:** Get imports information from files or project.

**Behavior:** Returns import statements and metadata for the given file(s) or project.

---

## find_dependencies — FindDependenciesMCPCommand

**File:** `commands/ast/dependencies.py`

**Description:** Find dependencies — where classes, functions, or modules are used.

**Behavior:** Accepts target (class/function/module); returns locations/usages that depend on it.

---

## get_class_hierarchy — GetClassHierarchyMCPCommand

**File:** `commands/ast/hierarchy.py`

**Description:** Get class hierarchy (inheritance tree).

**Behavior:** Builds inheritance tree for the project or file and returns parent/child class relationships.

---

## find_usages — FindUsagesMCPCommand

**File:** `commands/ast/usages.py`

**Description:** Find usages of methods, properties, classes, or functions.

**Behavior:** Accepts symbol (method/property/class/function); returns all usage locations.

---

## export_graph — ExportGraphMCPCommand

**File:** `commands/ast/graph.py`

**Description:** Export dependency graphs, class hierarchies, or call graphs. Goal: stable output (JSON or DOT) without failing on partial/missing data.

**Behavior:** Accepts graph type and scope; returns JSON or DOT representation of the graph.
