# Search Functionality Test Report

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-29  
**Test Method**: MCP Server Commands Only

## Executive Summary

Comprehensive testing of all search functionality types through MCP server. Found several issues with search quality and coverage.

## 1. Search Types Tested

### 1.1 Semantic Search (`semantic_search`)

**Status**: ⚠️ **Working but Low Quality**

**Tests Performed**:
1. Query: `"database worker process"` → ✅ Executed, but irrelevant results
2. Query: `"code analysis tool MCP server"` → ✅ Executed, but irrelevant results
3. Query: `"SQLite connection driver"` → ✅ Executed, but irrelevant results
4. Query: `"Unix socket communication"` → ✅ Executed, but irrelevant results
5. Query: `"worker manager process"` → ✅ Executed, but irrelevant results

**Results Analysis**:
- All queries return results from `test_data/bhlff_mcp_test/core/bvp/power_law/`
- All results have identical scores (~0.5), indicating poor relevance ranking
- Results are not semantically related to queries
- Same results returned for different queries

**Issues**:
- ❌ **Low relevance**: Results don't match query semantics
- ❌ **Poor ranking**: All results have similar scores
- ❌ **Limited scope**: Only returns results from test_data, not project code

**Recommendation**: 
- Review embedding model quality
- Check vectorization process
- Verify FAISS index quality
- Consider re-indexing with better embeddings

### 1.2 Full-Text Search (`fulltext_search`)

**Status**: ⚠️ **Partially Working**

**Tests Performed**:
1. Query: `"CodeDatabase"` → ✅ **Working** - Found 5 results in scripts
2. Query: `"def execute"` → ✅ **Working** - Found 5 results
3. Query: `"socket_path"` → ⚠️ **No results** - Should find in sqlite_proxy.py
4. Query: `"multiprocessing.Queue"` → ❌ **Error**: FTS5 syntax error
5. Query: `"class CodeDatabase"` → ✅ **Working** - Found results
6. Query: `"DBWorkerManager"` → ✅ **Working** - Found results

**Results Analysis**:
- Simple text queries work well
- Finds matches in scripts and test_data
- Cannot search for patterns with dots (FTS5 limitation)
- Cannot find code in main project (`code_analysis/` package)

**Issues**:
- ❌ **FTS5 Syntax Error**: Queries with dots (e.g., `multiprocessing.Queue`) fail
- ⚠️ **Limited Coverage**: Main project code not indexed
- ⚠️ **Pattern Matching**: Cannot search for complex patterns

**Error Example**:
```
fts5: syntax error near "."
Query: "multiprocessing.Queue"
```

**Recommendation**:
- Escape dots in FTS5 queries
- Index main project code (`code_analysis/`)
- Add pattern matching support

### 1.3 Class Search (`find_classes`)

**Status**: ⚠️ **Limited Coverage**

**Tests Performed**:
1. Pattern: `"Database"` → ✅ Found 1 class: `ResultsDatabase` (test_data)
2. Pattern: `"Worker"` → ❌ **No results** - Should find `DBWorkerManager`
3. Pattern: `"Driver"` → ❌ **No results** - Should find driver classes
4. Pattern: `"CodeDatabase"` → ❌ **No results** - Main class not found

**Results Analysis**:
- Only finds classes in `test_data/`
- Main project classes not indexed
- Pattern matching works (case-sensitive)

**Issues**:
- ❌ **Missing Main Code**: `code_analysis/` package not indexed
- ⚠️ **Case Sensitivity**: Pattern matching is case-sensitive
- ⚠️ **Limited Results**: Only test_data classes found

**Recommendation**:
- Index main project code
- Add case-insensitive option
- Verify indexing process includes all Python files

### 1.4 Entity Listing (`list_code_entities`)

**Status**: ✅ **Working**

**Tests Performed**:
1. Type: `class`, Pattern: `"Database"` → ✅ Found 10 classes
2. Type: `function`, Pattern: `"search"` → ✅ Found 10 functions
3. Type: `method`, Pattern: `"execute"` → ✅ Found 10 methods

**Results Analysis**:
- Works correctly for all entity types
- Pattern filtering works
- Returns proper metadata (docstrings, args, etc.)
- Limited to indexed code (test_data)

**Issues**:
- ⚠️ **Limited Coverage**: Only test_data indexed
- ✅ **Functionality**: Works as expected for indexed code

### 1.5 Usage Search (`find_usages`)

**Status**: ❌ **Not Working**

**Tests Performed**:
1. Entity: `class CodeDatabase` → ❌ **No usages found** (should find many)
2. Entity: `function create_driver` → ❌ **No usages found** (should find many)

**Results Analysis**:
- Always returns empty results
- Should find usages in scripts and main code
- Indicates indexing or query issue

**Issues**:
- ❌ **No Results**: Always returns empty
- ❌ **Main Code Not Indexed**: Cannot find usages in `code_analysis/`
- ❌ **Query Issue**: May be querying wrong index or table

**Recommendation**:
- Fix usage tracking in index
- Verify `find_usages` implementation
- Check database schema for usage tracking

### 1.6 AST Node Search (`search_ast_nodes`)

**Status**: ✅ **Working**

**Tests Performed**:
1. Node Type: `ClassDef` → ✅ Found classes
2. Node Type: `FunctionDef`, Pattern: `"search"` → ✅ Found functions

**Results Analysis**:
- Works correctly for AST node types
- Pattern matching works
- Returns proper AST information

**Issues**:
- ⚠️ **Limited Coverage**: Only test_data indexed
- ✅ **Functionality**: Works as expected

## 2. Coverage Analysis

### 2.1 Indexed Code

**Currently Indexed**:
- ✅ `test_data/bhlff_mcp_test/` - 856 files, 5,340 chunks
- ✅ `scripts/` - Test scripts indexed
- ❌ `code_analysis/` - **NOT INDEXED** (main project code)

### 2.2 Missing Coverage

**Not Indexed**:
- ❌ `code_analysis/core/` - Core functionality
- ❌ `code_analysis/commands/` - Command implementations
- ❌ `code_analysis/cli/` - CLI interfaces
- ❌ Main project Python files

**Impact**:
- Cannot search main project code
- Cannot find classes like `CodeDatabase`, `DBWorkerManager`
- Cannot find usages of main project entities
- Semantic search only works on test_data

## 3. Issues Summary

### 3.1 Critical Issues

1. **❌ Main Project Code Not Indexed**
   - `code_analysis/` package not in database
   - Cannot search main functionality
   - Cannot find main project classes/functions

2. **❌ Semantic Search Low Quality**
   - Irrelevant results
   - Poor ranking (all scores ~0.5)
   - Same results for different queries

3. **❌ FTS5 Syntax Error**
   - Queries with dots fail
   - Need escaping or different query format

4. **❌ Usage Search Not Working**
   - Always returns empty results
   - Cannot find usages of entities

### 3.2 Moderate Issues

1. **⚠️ Limited Test Coverage**
   - Only test_data indexed
   - Main project code missing

2. **⚠️ Case Sensitivity**
   - Pattern matching is case-sensitive
   - May miss matches

3. **⚠️ Pattern Limitations**
   - Cannot search complex patterns
   - FTS5 limitations

## 4. Recommendations

### 4.1 Immediate Actions

1. **Index Main Project Code**
   ```python
   # Run update_indexes on code_analysis/ directory
   update_indexes(root_dir="/home/vasilyvz/projects/tools/code_analysis", 
                  include_patterns=["code_analysis/**/*.py"])
   ```

2. **Fix FTS5 Query Escaping**
   - Escape dots in queries: `multiprocessing.Queue` → `multiprocessing Queue`
   - Or use different query format

3. **Fix Usage Tracking**
   - Verify `find_usages` implementation
   - Check database schema
   - Ensure usage relationships are indexed

### 4.2 Semantic Search Improvements

1. **Review Embedding Model**
   - Check if embeddings are generated correctly
   - Verify FAISS index quality
   - Consider re-indexing with better model

2. **Improve Ranking**
   - Review similarity calculation
   - Add relevance scoring
   - Filter low-quality results

3. **Add Query Expansion**
   - Expand queries with synonyms
   - Use context-aware embeddings

### 4.3 Testing Improvements

1. **Add Search Tests**
   - Test all search types
   - Verify result quality
   - Test edge cases

2. **Monitor Search Quality**
   - Track search success rates
   - Monitor result relevance
   - Collect user feedback

## 5. Test Results Summary

| Search Type | Status | Coverage | Quality | Notes |
|------------|--------|----------|---------|-------|
| `semantic_search` | ⚠️ Working | Limited | ❌ Low | Irrelevant results, poor ranking |
| `fulltext_search` | ⚠️ Partial | Limited | ⚠️ Medium | FTS5 errors, main code missing |
| `find_classes` | ⚠️ Limited | Limited | ⚠️ Medium | Only test_data, main code missing |
| `list_code_entities` | ✅ Working | Limited | ✅ Good | Works but limited scope |
| `find_usages` | ❌ Broken | N/A | ❌ None | Always returns empty |
| `search_ast_nodes` | ✅ Working | Limited | ✅ Good | Works but limited scope |

## 6. Conclusion

### Current State

- ✅ **Basic Functionality**: Most search types execute without errors
- ⚠️ **Coverage**: Limited to test_data, main project code not indexed
- ❌ **Quality**: Semantic search returns irrelevant results
- ❌ **Completeness**: Usage search not working, FTS5 errors

### Priority Fixes

1. **HIGH**: Index main project code (`code_analysis/`)
2. **HIGH**: Fix usage search (`find_usages`)
3. **MEDIUM**: Fix FTS5 query escaping
4. **MEDIUM**: Improve semantic search quality
5. **LOW**: Add case-insensitive pattern matching

### Next Steps

1. Run `update_indexes` to include `code_analysis/` package
2. Fix `find_usages` implementation
3. Add FTS5 query escaping
4. Review and improve semantic search embeddings
5. Add comprehensive search tests

---

**Note**: This analysis was performed exclusively through MCP server commands, demonstrating both the tool's capabilities and current limitations.

