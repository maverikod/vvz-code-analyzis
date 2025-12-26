# AST Vectorization Status Report

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-26

## Overview

This document describes the current status of AST tree vectorization in the code analysis system.

## Important Clarification

**AST trees themselves are NOT vectorized**. The system vectorizes **docstrings and comments** extracted from AST trees, with precise binding to AST nodes.

### What is Vectorized

1. **Docstrings** - extracted from classes, methods, functions
2. **Comments** - extracted from code
3. **File-level docstrings** - module docstrings

### What is NOT Vectorized

1. **AST tree structure** - stored as JSON in `ast_trees` table
2. **Code structure** - classes, methods, functions are stored in separate tables
3. **Code content** - actual code is not vectorized

## Current Architecture

### Phase 1: AST Extraction and Chunking

1. **AST Tree Parsing**: Parse Python files to AST
2. **AST Tree Storage**: Store AST as JSON in `ast_trees` table
3. **Docstring Extraction**: Extract docstrings/comments from AST nodes
4. **Chunking**: Chunk text using SVO chunker service
5. **AST Binding**: Resolve entity IDs (class_id, function_id, method_id) from database
6. **Chunk Storage**: Save chunks to `code_chunks` table with:
   - `vector_id = NULL` (will be set by worker)
   - `embedding_vector = NULL` (may be set by chunker if it returns embeddings)
   - AST binding: `class_id`, `function_id`, `method_id`, `line`, `ast_node_type`

### Phase 2: Vectorization (Background Worker)

1. **Get Non-Vectorized Chunks**: Query chunks where `vector_id IS NULL`
2. **Get Embeddings**: 
   - If chunk has `embedding_vector` in DB → use it
   - Otherwise → request from SVO embedding service
3. **Add to FAISS**: Add embedding to FAISS index, get `vector_id`
4. **Update Database**: Set `vector_id` and `embedding_model` in `code_chunks` table

## Current Status

### Database Statistics

- **AST Trees**: 233 trees stored (for 234 files)
- **Total Chunks**: 314 chunks
- **Vectorized Chunks**: 0 (0%)
- **Non-Vectorized Chunks**: 314 (100%)
- **Chunks with AST Binding**: 246 (78.3%)

### Chunk Types

- **docstring**: 239 chunks
- **file_docstring**: 65 chunks
- **comment**: 10 chunks

### Processing Status

- **Chunks with embeddings but no vector_id**: 4 chunks (ready for FAISS)
- **Chunks without embeddings**: 313 chunks (need embeddings from service)

## Worker Status

- **Worker Process**: Running (PID: 25911)
- **Circuit Breaker**: CLOSED (services available)
- **Chunker Service**: Available (health check passed)

## Why Chunks Are Not Vectorized

Possible reasons:

1. **Worker just started** - poll_interval is 30 seconds, may need time to start processing
2. **Services unavailable** - chunker/embedding services may be down (but health check shows available)
3. **Worker logs not visible** - worker runs in separate process, logs may be in different location
4. **Circuit breaker blocking** - if services were unavailable, circuit breaker may have opened

## Next Steps

1. **Monitor worker logs** - check for processing cycles
2. **Verify service connectivity** - ensure chunker/embedding services are accessible
3. **Check FAISS index** - verify index file exists and is writable
4. **Review circuit breaker state** - ensure it's not blocking requests

## AST Tree Storage

AST trees are stored separately in `ast_trees` table:
- **Purpose**: Fast AST queries without re-parsing
- **Format**: JSON serialization
- **Usage**: AST-based analysis, refactoring, dependency tracking
- **Vectorization**: NOT vectorized (only docstrings/comments are vectorized)

## Conclusion

The system is designed to vectorize **docstrings and comments with AST binding**, not the AST trees themselves. This approach provides:

1. **Semantic search** over documentation
2. **Precise binding** to code structure (via AST node IDs)
3. **Efficient storage** (AST trees stored separately as JSON)
4. **Fast queries** (can query AST structure without vector search)

Current status shows all chunks are ready for vectorization but none have been processed yet. Worker is running and services are available, so processing should begin soon.

