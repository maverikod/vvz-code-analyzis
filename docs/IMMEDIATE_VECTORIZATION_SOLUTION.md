# Immediate Vectorization Solution

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-01-27

## Executive Summary

This document provides a solution for **immediate vectorization** of files after they are written to disk and database is updated. The solution ensures that files are vectorized as soon as possible, without waiting for the vectorization worker's polling cycle.

## Problem Statement

**Current Situation**:
- Files are written to disk
- Database is updated (AST, CST, entities)
- Files are marked for chunking via `mark_file_needs_chunking`
- Vectorization worker processes files in polling cycles (every 30 seconds)
- **Delay**: Files may wait up to 30 seconds before being vectorized

**User Requirement**:
- After file write and database update, file should be **immediately vectorized**
- No waiting for worker polling cycle

## Solution Architecture

### Approach: Hybrid Immediate + Worker Fallback

**Strategy**:
1. **Try immediate vectorization** after database update
2. **If successful**: File is vectorized immediately (chunks with embeddings saved)
3. **If failed or SVO unavailable**: Mark for worker processing (non-blocking fallback)

**Benefits**:
- ✅ Fast vectorization when SVO is available
- ✅ Non-blocking (doesn't fail file write if vectorization fails)
- ✅ Automatic fallback to worker if immediate vectorization unavailable
- ✅ No changes to worker architecture needed

## Implementation

### 1. New Method: `vectorize_file_immediately`

**Location**: `code_analysis/core/database/files.py` or `code_analysis/core/vectorization_helper.py`

**Method Signature**:
```python
async def vectorize_file_immediately(
    self,
    file_id: int,
    project_id: str,
    file_path: str,
    svo_client_manager: Optional[Any] = None,
    faiss_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Immediately chunk and vectorize a file after database update.
    
    This method attempts to vectorize the file immediately. If SVO client
    manager is not available or chunking fails, file is marked for worker
    processing (non-blocking fallback).
    
    Process:
    1. Check if SVO client manager is available
    2. Read file content and parse AST
    3. Call DocstringChunker.process_file() to chunk and get embeddings
    4. If successful, chunks are saved with embeddings
    5. Worker will add vectors to FAISS in next cycle
    6. If failed, mark file for worker processing
    
    Args:
        file_id: File ID
        project_id: Project ID
        file_path: File path (absolute)
        svo_client_manager: Optional SVO client manager
        faiss_manager: Optional FAISS manager
        
    Returns:
        Dictionary with vectorization result:
        {
            "success": bool,
            "chunked": bool,  # True if chunking succeeded
            "chunks_created": int,
            "vectorized": bool,  # True if embeddings were created
            "marked_for_worker": bool,  # True if marked for worker processing
            "error": Optional[str]
        }
    """
```

**Implementation Details**:

1. **Check SVO Availability**:
   ```python
   if not svo_client_manager:
       # Mark for worker and return
       self.mark_file_needs_chunking(file_path, project_id)
       return {"chunked": False, "marked_for_worker": True, ...}
   ```

2. **Read and Parse File**:
   ```python
   file_content = Path(file_path).read_text(encoding="utf-8")
   tree = ast.parse(file_content, filename=file_path)
   ```

3. **Create Chunker and Process**:
   ```python
   from ..docstring_chunker_pkg import DocstringChunker
   
   chunker = DocstringChunker(
       database=self,
       svo_client_manager=svo_client_manager,
       faiss_manager=faiss_manager,
       min_chunk_length=30,
   )
   
   chunks_created = await chunker.process_file(
       file_id=file_id,
       project_id=project_id,
       file_path=file_path,
       tree=tree,
       file_content=file_content,
   )
   ```

4. **Error Handling**:
   - If any step fails, mark file for worker processing
   - Log errors but don't fail the operation
   - Return detailed result for caller

### 2. Integration into `update_file_data`

**Option A**: Make `update_file_data` async and call vectorization internally

**Option B** (Recommended): Create separate async wrapper method

**Method**: `update_and_vectorize_file`

```python
async def update_and_vectorize_file(
    self,
    file_path: str,
    project_id: str,
    root_dir: Path,
    svo_client_manager: Optional[Any] = None,
    faiss_manager: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Update database and immediately vectorize file.
    
    This is the recommended method for file write operations.
    It combines update_file_data + vectorize_file_immediately.
    
    Args:
        file_path: File path (relative to root_dir or absolute)
        project_id: Project ID
        root_dir: Project root directory
        svo_client_manager: Optional SVO client manager
        faiss_manager: Optional FAISS manager
        
    Returns:
        Combined result from update_file_data + vectorize_file_immediately
    """
    # Step 1: Update database
    update_result = self.update_file_data(
        file_path=file_path,
        project_id=project_id,
        root_dir=root_dir
    )
    
    if not update_result.get("success"):
        return update_result
    
    # Step 2: Try immediate vectorization
    file_id = update_result.get("file_id")
    abs_path = update_result.get("file_path")
    
    if svo_client_manager:
        try:
            vectorization_result = await self.vectorize_file_immediately(
                file_id=file_id,
                project_id=project_id,
                file_path=abs_path,
                svo_client_manager=svo_client_manager,
                faiss_manager=faiss_manager,
            )
        except Exception as e:
            logger.warning(f"Immediate vectorization failed: {e}")
            # Fallback: mark for worker
            self.mark_file_needs_chunking(abs_path, project_id)
            vectorization_result = {
                "chunked": False,
                "marked_for_worker": True,
                "error": str(e)
            }
    else:
        # No SVO manager, mark for worker
        self.mark_file_needs_chunking(abs_path, project_id)
        vectorization_result = {
            "chunked": False,
            "marked_for_worker": True
        }
    
    # Combine results
    update_result["vectorization"] = vectorization_result
    return update_result
```

### 3. Integration Points

#### 3.1 CST Compose Command

**File**: `code_analysis/commands/cst_compose_module_command.py`

**After file write**:
```python
if apply:
    backup_path = write_with_backup(target, new_source, create_backup=create_backup)
    
    # Update database and vectorize immediately
    try:
        project_id = get_project_id(root_path)
        svo_manager = get_svo_client_manager()  # Helper function
        faiss_manager = get_faiss_manager()  # Helper function
        
        if project_id:
            result = await database.update_and_vectorize_file(
                file_path=str(target.relative_to(root_path)),
                project_id=project_id,
                root_dir=root_path,
                svo_client_manager=svo_manager,
                faiss_manager=faiss_manager,
            )
            
            if result.get("vectorization", {}).get("chunked"):
                logger.info(f"File vectorized immediately: {result['vectorization']['chunks_created']} chunks")
    except Exception as e:
        logger.error(f"Error updating/vectorizing: {e}", exc_info=True)
        # Don't fail operation
```

**Note**: If command is not async, use `asyncio.create_task()` or mark for worker only.

#### 3.2 File Watcher

**File**: `code_analysis/core/file_watcher_pkg/processor.py`

**After detecting file change**:
```python
# Update database
update_result = self.database.update_file_data(...)

if update_result.get("success"):
    # Try immediate vectorization (if async context available)
    # Otherwise, mark for worker
    if hasattr(self, '_svo_client_manager') and self._svo_client_manager:
        try:
            vectorization_result = await self.database.vectorize_file_immediately(
                file_id=update_result.get("file_id"),
                project_id=project_id,
                file_path=file_path,
                svo_client_manager=self._svo_client_manager,
                faiss_manager=getattr(self, '_faiss_manager', None),
            )
        except Exception:
            # Fallback: mark for worker
            self.database.mark_file_needs_chunking(file_path, project_id)
    else:
        # Mark for worker
        self.database.mark_file_needs_chunking(file_path, project_id)
```

#### 3.3 Other File Write Operations

**Pattern**: Same as CST Compose
- After file write
- Call `update_and_vectorize_file` (async) or `update_file_data` + `mark_file_needs_chunking` (sync)

### 4. Helper Functions

**File**: `code_analysis/core/vectorization_helper.py` (NEW)

**Functions**:
```python
def get_svo_client_manager() -> Optional[Any]:
    """Get SVO client manager from config or global state."""
    # Implementation depends on architecture
    pass

def get_faiss_manager() -> Optional[Any]:
    """Get FAISS manager from config or global state."""
    # Implementation depends on architecture
    pass
```

## Vectorization Process Flow

### Current Flow (Worker Only):
```
File Write → Database Update → mark_file_needs_chunking → 
Worker Polling (30s) → Chunking → Embedding → FAISS
```

### New Flow (Immediate + Worker):
```
File Write → Database Update → 
  ├─ Try Immediate Vectorization (if SVO available)
  │   ├─ Success: Chunking + Embedding → Chunks saved with embeddings
  │   │   └─ Worker adds to FAISS in next cycle
  │   └─ Failure: mark_file_needs_chunking → Worker processes
  └─ No SVO: mark_file_needs_chunking → Worker processes
```

## Benefits

1. **Fast Vectorization**: Files are vectorized immediately when SVO is available
2. **Non-Blocking**: File writes don't fail if vectorization fails
3. **Automatic Fallback**: Worker handles vectorization if immediate fails
4. **No Worker Changes**: Worker continues to work as before
5. **Backward Compatible**: Works even if SVO is not available

## Considerations

### 1. Async Context

**Challenge**: Many file write operations are synchronous.

**Solutions**:
- **Option A**: Make operations async (requires refactoring)
- **Option B**: Use `asyncio.create_task()` for background vectorization
- **Option C**: Mark for worker only in sync contexts (simpler)

**Recommended**: **Option C** for now, Option B for future enhancement.

### 2. SVO Client Manager Access

**Challenge**: Need to get SVO client manager in various contexts.

**Solutions**:
- Pass as parameter (explicit, but requires changes)
- Get from global state/config (simpler, but less explicit)
- Store in database instance (if available)

**Recommended**: Helper functions that try multiple sources.

### 3. Error Handling

**Strategy**: 
- Never fail file write if vectorization fails
- Log all errors clearly
- Always have fallback (mark for worker)

### 4. Performance

**Impact**:
- Immediate vectorization adds latency to file write operations
- Typically 100-500ms per file (depends on SVO service)
- Can be made async/non-blocking

**Mitigation**:
- Make vectorization async (non-blocking)
- Use background tasks where possible
- Worker fallback ensures no data loss

## Testing

### Test Cases

1. **Immediate Vectorization Success**:
   - Write file
   - SVO available
   - Verify chunks created with embeddings
   - Verify file NOT marked for worker

2. **Immediate Vectorization Failure**:
   - Write file
   - SVO available but fails
   - Verify file marked for worker
   - Verify worker processes file later

3. **No SVO Available**:
   - Write file
   - No SVO manager
   - Verify file marked for worker
   - Verify worker processes file

4. **Async Context**:
   - Test in async context (CST compose if async)
   - Test in sync context (fallback to worker)

5. **Error Recovery**:
   - Simulate various errors
   - Verify fallback works
   - Verify file write succeeds

## Integration with Unified Plan

This solution integrates into `docs/UNIFIED_IMPLEMENTATION_PLAN.md`:

- **Phase 2.5**: Add `vectorize_file_immediately` method
- **Phase 2.9**: Integrate into `update_file_data` (optional)
- **Phase 3**: Add vectorization calls to all file write operations
- **Phase 4**: Add vectorization to file watcher

## Code References

- `code_analysis/core/docstring_chunker_pkg/docstring_chunker.py` - `DocstringChunker.process_file()`
- `code_analysis/core/vectorization_worker_pkg/chunking.py` - `_request_chunking_for_files()`
- `code_analysis/core/database/files.py` - `mark_file_needs_chunking()`

## Conclusion

**Solution**: Hybrid immediate + worker fallback approach
- ✅ Fast when SVO available
- ✅ Reliable fallback to worker
- ✅ Non-blocking
- ✅ Backward compatible

**Implementation**: Add `vectorize_file_immediately` method and integrate into file write operations and file watcher.

