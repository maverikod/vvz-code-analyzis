# Feature Request: Automatic Job Status Polling for Queued Commands

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-30

## Problem Statement

Currently, when a command with `use_queue=True` is executed, the handler returns a `job_id` immediately. The client must manually poll the job status using `queue_get_job_status` with `sleep()` calls between checks. This is cumbersome and error-prone.

## Proposed Solution

Add support for automatic job status polling directly in the command handler when a `poll_interval` parameter is specified.

## Requirements

### 1. Parameter Support

Add optional `poll_interval` and `max_wait_time` parameters to all commands with `use_queue=True`:

- **`poll_interval`** (float, optional): Interval in seconds between status checks. Must be > 0.
- **`max_wait_time`** (float, optional): Maximum time to wait in seconds. Must be > 0 if specified. Default: no limit.

### 2. Handler Behavior

When a command with `use_queue=True` is called and `poll_interval` is specified in parameters:

1. **Queue the job** as usual (create job, add to queue, start job)
2. **Instead of returning `job_id`**, automatically poll job status at specified interval
3. **Return final result** when job completes (success or failure)
4. **Respect `max_wait_time`** - return timeout error if exceeded

### 3. Implementation Location

The polling logic should be implemented in the command handler (likely in `handlers.py` or similar), not in individual commands. This ensures:
- Consistent behavior across all queued commands
- No need to modify each command individually
- Centralized polling logic

### 4. Example Flow

```python
# Current behavior (manual polling required):
result = call_server("comprehensive_analysis", {"root_dir": "/path"})
job_id = result["job_id"]
while True:
    status = queue_get_job_status(job_id)
    if status["status"] in ["completed", "failed"]:
        break
    sleep(1)  # Manual sleep required

# Proposed behavior (automatic polling):
result = call_server("comprehensive_analysis", {
    "root_dir": "/path",
    "poll_interval": 1.0,  # Automatic polling every 1 second
    "max_wait_time": 3600  # Timeout after 1 hour
})
# result contains final job result, no manual polling needed
```

### 5. Error Handling

- If `poll_interval <= 0`: Return validation error before queuing job
- If `max_wait_time <= 0`: Return validation error before queuing job
- If `max_wait_time` exceeded: Return timeout error with code `POLL_TIMEOUT`
- If job fails: Return job error result
- If job completes: Return job success result

### 6. Progress Logging

During polling, log progress updates:
- Job status changes
- Progress percentage changes
- Description updates

### 7. Backward Compatibility

- If `poll_interval` is not specified, behavior remains unchanged (return `job_id`)
- Existing code without `poll_interval` continues to work as before
- No breaking changes to existing API

## Implementation Details

### Handler Modification

In the command handler, after detecting `use_queue=True`:

```python
# Pseudo-code
if use_queue:
    # Check for poll_interval parameter
    poll_interval = params.get("poll_interval")
    
    if poll_interval is not None:
        # Validate poll_interval
        if poll_interval <= 0:
            return ErrorResult(
                message="poll_interval must be > 0",
                code="INVALID_POLL_INTERVAL"
            )
        
        # Validate max_wait_time if specified
        max_wait_time = params.get("max_wait_time")
        if max_wait_time is not None and max_wait_time <= 0:
            return ErrorResult(
                message="max_wait_time must be > 0",
                code="INVALID_MAX_WAIT_TIME"
            )
        
        # Remove poll_interval and max_wait_time from params before queuing
        command_params = {
            k: v for k, v in params.items() 
            if k not in ["poll_interval", "max_wait_time"]
        }
        
        # Queue job as usual
        job_id = queue_job(command_name, command_params)
        
        # Poll until completion
        start_time = time.time()
        while True:
            # Check timeout
            if max_wait_time and (time.time() - start_time) >= max_wait_time:
                return ErrorResult(
                    message=f"Polling timeout after {max_wait_time} seconds",
                    code="POLL_TIMEOUT"
                )
            
            # Get job status
            job = get_job(job_id)
            if not job:
                return ErrorResult(
                    message=f"Job {job_id} not found",
                    code="JOB_NOT_FOUND"
                )
            
            # Check if done
            if job.status in ["completed", "failed", "stopped"]:
                return job.result  # Return final result
            
            # Wait before next check
            await asyncio.sleep(poll_interval)
    else:
        # Normal behavior: return job_id
        job_id = queue_job(command_name, params)
        return {"job_id": job_id, "status": "pending"}
```

## Benefits

1. **Simplified client code**: No need for manual polling loops
2. **Consistent behavior**: All queued commands support automatic polling
3. **Better UX**: Single call returns final result
4. **Error handling**: Centralized timeout and error handling
5. **Backward compatible**: Existing code continues to work

## Testing Requirements

1. Test with `poll_interval` specified - should return final result
2. Test without `poll_interval` - should return `job_id` (backward compatibility)
3. Test with invalid `poll_interval` (<= 0) - should return validation error
4. Test with `max_wait_time` - should timeout correctly
5. Test with long-running jobs - should poll correctly
6. Test with failed jobs - should return error result

## Related Files

- Command handler (likely `mcp_proxy_adapter/handlers.py` or similar)
- Queue manager integration
- Command base class (if parameter validation needed there)

## Priority

**High** - This feature significantly improves developer experience when working with long-running commands.

