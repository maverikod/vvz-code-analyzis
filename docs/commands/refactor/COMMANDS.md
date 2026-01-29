# Refactor Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

All in `commands/refactor_mcp_commands.py`. Core logic in `core/refactorer_pkg/` (extractor, splitter, file_splitter, validators). Schema from `get_schema()`; metadata from `metadata()`.

---

## extract_superclass — ExtractSuperclassMCPCommand

**Description:** Extract a new superclass from a class, moving selected methods to the base class and updating the child.

**Behavior:** Accepts file path, class name, and list of methods to move; creates new base class in same file or new file, updates child class to inherit and removes moved methods; validates completeness and docstrings.

---

## split_class — SplitClassMCPCommand

**Description:** Split a large class into multiple classes (e.g. by grouping methods).

**Behavior:** Accepts file path, class name, and split configuration; creates new classes and moves methods; updates references and validates.

---

## split_file_to_package — SplitFileToPackageMCPCommand

**Description:** Split a single Python file into a package (directory with __init__.py and modules).

**Behavior:** Accepts file path and optional mapping of symbols to modules; creates package layout, moves classes/functions to modules, builds __init__.py with re-exports; validates imports and syntax.
