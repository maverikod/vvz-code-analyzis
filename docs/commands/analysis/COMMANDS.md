# Analysis Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

**analyze_complexity:** `commands/analyze_complexity_mcp.py`. **find_duplicates:** `commands/find_duplicates_mcp.py`. **comprehensive_analysis:** `commands/comprehensive_analysis_mcp.py`. **semantic_search:** `commands/semantic_search_mcp.py`. Schema from `get_schema()`; metadata from `metadata()`.

---

## analyze_complexity — AnalyzeComplexityMCPCommand

**Description:** Analyze cyclomatic complexity for functions and methods.

**Behavior:** Accepts project or file; uses ComplexityAnalyzer to compute complexity metrics per function/method; returns list with complexity scores and locations.

---

## find_duplicates — FindDuplicatesMCPCommand

**Description:** Find duplicate or near-duplicate code (e.g. by AST hash or similarity).

**Behavior:** Accepts project/file scope; uses DuplicateDetector to find duplicate blocks or similar functions; returns pairs or groups of duplicates with similarity score.

---

## comprehensive_analysis — ComprehensiveAnalysisMCPCommand

**Description:** Comprehensive code analysis combining multiple analysis types (placeholders, stubs, empty methods, imports not at top, long files, flake8, mypy, docstrings).

**Behavior:** Runs ComprehensiveAnalyzer over project or file; returns combined report (issues by category).

---

## semantic_search — SemanticSearchMCPCommand

**Description:** Semantic search over code using vector embeddings (and optionally FAISS).

**Behavior:** Accepts query text and optional filters; embeds query, searches FAISS index (or vector DB), returns relevant chunks/code with scores.
