# Queue Manager Integration - Detailed Analysis

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Overview

The `mcp-proxy-adapter` framework includes a comprehensive queue management system (`queuemgr`) that enables asynchronous execution of long-running commands. This document provides a detailed analysis of how the queue manager works and how to use it effectively.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Initialization and Configuration](#initialization-and-configuration)
3. [Command Execution Flow](#command-execution-flow)
4. [Queue Manager API](#queue-manager-api)
5. [Job Lifecycle](#job-lifecycle)
6. [Progress Tracking](#progress-tracking)
7. [Error Handling](#error-handling)
8. [Configuration Options](#configuration-options)
9. [Best Practices](#best-practices)
10. [Examples](#examples)

## Architecture Overview

### Components

1. **QueueManagerIntegration** (`mcp_proxy_adapter.integrations.queuemgr_integration`)
   - High-level wrapper around `queuemgr` library
   - Provides MCP-compatible interface
   - Handles job status conversion and normalization

2. **QueueJobBase** (`mcp_proxy_adapter.integrations.queuemgr_integration.QueueJobBase`)
   - Base class for all queue jobs
   - Extends `queuemgr.jobs.base.QueueJobBase`
   - Provides helper methods: `set_status()`, `set_progress()`, `set_description()`, `set_mcp_result()`, `set_mcp_error()`

3. **CommandExecutionJob** (`mcp_proxy_adapter.commands.queue.jobs.CommandExecutionJob`)
   - Special job class that executes registered commands
   - Automatically handles command discovery and execution
   - Supports progress tracking for long-running commands

4. **Global Queue Manager**
   - Singleton instance accessible via `get_global_queue_manager()`
   - Initialized via `init_global_queue_manager()` in startup event
   - Shutdown via `shutdown_global_queue_manager()` in shutdown event

### Data Flow

```
Client Request
    ↓
execute_command() in handlers.py
    ↓
Check use_queue flag
    ↓
[If use_queue=True]
    ↓
Create CommandExecutionJob
    ↓
Add to queue via queue_manager.add_job()
    ↓
Start job via queue_manager.start_job()
    ↓
Return job_id to client
    ↓
[Client polls status]
    ↓
queue_get_job_status command
    ↓
Return job status, progress, result
```

## Initialization and Configuration

### Startup Event

The queue manager must be initialized during FastAPI startup:

```python
from mcp_proxy_adapter.integrations.queuemgr_integration import init_global_queue_manager

@app.on_event("startup")
async def startup():
    # Load configuration
    config = load_config()
    
    # Initialize queue manager
    await init_global_queue_manager(
        registry_path=config.queue_manager.registry_path,
        shutdown_timeout=config.queue_manager.shutdown_timeout,
        max_concurrent_jobs=config.queue_manager.max_concurrent_jobs,
        in_memory=config.queue_manager.in_memory,
        max_queue_size=config.queue_manager.max_queue_size,
        per_job_type_limits=config.queue_manager.per_job_type_limits,
        completed_job_retention_seconds=config.queue_manager.completed_job_retention_seconds,
    )
```

### Configuration File

```json
{
  "queue_manager": {
    "enabled": true,
    "in_memory": true,
    "registry_path": null,
    "shutdown_timeout": 30.0,
    "max_concurrent_jobs": 5,
    "max_queue_size": null,
    "per_job_type_limits": null,
    "completed_job_retention_seconds": 21600
  }
}
```

### Configuration Parameters

- **enabled**: Enable/disable queue manager (default: true)
- **in_memory**: Use temporary file (deleted on shutdown) vs persistent file (default: true)
- **registry_path**: Path to queue registry file (ignored if in_memory=true)
- **shutdown_timeout**: Timeout for graceful shutdown in seconds (default: 30.0)
- **max_concurrent_jobs**: Maximum number of jobs running simultaneously (default: 10)
- **max_queue_size**: Maximum number of non-completed jobs. If reached, oldest non-completed job is deleted (default: null = no limit)
- **per_job_type_limits**: Dict mapping job_type to max count (default: null = no limits)
- **completed_job_retention_seconds**: How long to keep completed jobs before cleanup (default: 21600 = 6 hours). Set to 0 to keep indefinitely.

### Shutdown Event

```python
from mcp_proxy_adapter.integrations.queuemgr_integration import shutdown_global_queue_manager

@app.on_event("shutdown")
async def shutdown():
    await shutdown_global_queue_manager()
```

## Command Execution Flow

### 1. Command Registration

Commands are registered with the `use_queue` flag:

```python
from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult

class AnalyzeProjectCommand(Command):
    name = "analyze_project"
    use_queue = True  # Enable queue execution
    
    async def execute(self, root_dir: str, force: bool = False, **kwargs):
        # Long-running analysis
        result = await analyze_project_impl(root_dir, force)
        return SuccessResult(data=result)
```

### 2. Request Handling

When a command with `use_queue=True` is called:

```python
# In handlers.py execute_command()

use_queue = getattr(command_class, "use_queue", False)

if use_queue:
    # Get queue manager
    queue_manager = await get_global_queue_manager()
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Prepare job parameters
    job_params = {
        "command": command_name,
        "params": params or {},
        "context": context,
        "auto_import_modules": hooks.get_auto_import_modules(),
    }
    
    # Add job to queue
    await queue_manager.add_job(CommandExecutionJob, job_id, job_params)
    
    # Start job automatically
    await queue_manager.start_job(job_id)
    
    # Return job_id instead of result
    return {
        "success": True,
        "job_id": job_id,
        "status": "running",
        "message": f"Command '{command_name}' has been queued for execution",
    }
```

### 3. Job Execution

`CommandExecutionJob` executes the command in a separate process:

```python
class CommandExecutionJob(QueueJobBase):
    def run(self):
        # Get command name and params from job parameters
        command_name = self.mcp_params["command"]
        command_params = self.mcp_params["params"]
        context = self.mcp_params.get("context", {})
        
        # Import command registry in child process
        from mcp_proxy_adapter.commands.command_registry import registry
        
        # Get command class
        command_class = registry.get_command(command_name)
        
        # Execute command
        result = asyncio.run(command_class.run(**command_params, context=context))
        
        # Store result
        self.set_mcp_result(result.to_dict())
```

## Queue Manager API

### Core Methods

#### `add_job(job_class, job_id, params) -> QueueJobResult`

Adds a job to the queue without starting it.

```python
result = await queue_manager.add_job(
    job_class=MyJobClass,
    job_id="unique-job-id",
    params={"param1": "value1", "param2": "value2"}
)
```

**Behavior:**
- Validates job parameters
- Enforces `max_queue_size` and `per_job_type_limits` by deleting oldest non-completed jobs if needed
- Returns `QueueJobResult` with status `PENDING`

#### `start_job(job_id) -> QueueJobResult`

Starts a pending job.

```python
result = await queue_manager.start_job("unique-job-id")
```

**Behavior:**
- Changes job status from `PENDING` to `RUNNING`
- Launches job in separate process (spawn mode for CUDA compatibility)
- Returns `QueueJobResult` with status `RUNNING`

#### `stop_job(job_id) -> QueueJobResult`

Stops a running job.

```python
result = await queue_manager.stop_job("unique-job-id")
```

**Behavior:**
- Attempts to gracefully stop the job process
- Changes status to `STOPPED` or `FAILED`
- Handles timeout/IPC errors gracefully

#### `delete_job(job_id) -> QueueJobResult`

Deletes a job from the queue.

```python
result = await queue_manager.delete_job("unique-job-id")
```

**Behavior:**
- Removes job from queue registry
- Stops job if running
- Returns status `DELETED`

#### `get_job_status(job_id) -> QueueJobResult`

Gets current status of a job.

```python
result = await queue_manager.get_job_status("unique-job-id")
# Returns:
# {
#   "job_id": "unique-job-id",
#   "status": "running",  # pending, running, completed, failed, stopped, deleted
#   "result": {...},      # Job result (if completed)
#   "error": None,        # Error message (if failed)
#   "progress": 45,       # Progress percentage (0-100)
#   "description": "Processing files...",  # Current description
# }
```

#### `get_job_logs(job_id) -> Dict[str, Any]`

Gets stdout and stderr logs for a job.

```python
logs = await queue_manager.get_job_logs("unique-job-id")
# Returns:
# {
#   "job_id": "unique-job-id",
#   "stdout": ["line1", "line2", ...],
#   "stderr": ["error1", "error2", ...],
#   "stdout_lines": 10,
#   "stderr_lines": 2,
# }
```

#### `list_jobs() -> List[QueueJobResult]`

Lists all jobs in the queue.

```python
jobs = await queue_manager.list_jobs()
# Returns list of QueueJobResult objects
```

#### `get_queue_health() -> Dict[str, Any]`

Gets queue system health information.

```python
health = await queue_manager.get_queue_health()
# Returns:
# {
#   "status": "healthy",
#   "running": True,
#   "total_jobs": 10,
#   "pending_jobs": 2,
#   "running_jobs": 1,
#   "completed_jobs": 5,
#   "failed_jobs": 2,
#   "registry_path": "/path/to/registry.jsonl",
#   "max_concurrent_jobs": 5,
# }
```

## Job Lifecycle

### Status Transitions

```
PENDING → RUNNING → COMPLETED
              ↓
           FAILED
              ↓
          STOPPED
              ↓
          DELETED
```

### Status Descriptions

- **PENDING**: Job is queued but not yet started
- **RUNNING**: Job is currently executing
- **COMPLETED**: Job finished successfully
- **FAILED**: Job encountered an error
- **STOPPED**: Job was stopped (manually or timeout)
- **DELETED**: Job was removed from queue

### Automatic Cleanup

The queue manager automatically cleans up old completed jobs:

- Runs periodic cleanup task (every hour or `retention_period/6`, whichever is smaller)
- Deletes completed/failed jobs older than `completed_job_retention_seconds`
- Only affects completed/failed jobs; running/pending jobs are never auto-deleted

## Progress Tracking

### Updating Progress in Jobs

Jobs can update their progress using helper methods:

```python
class MyLongRunningJob(QueueJobBase):
    def run(self):
        total_items = 100
        
        for i in range(total_items):
            # Update progress (0-100)
            progress = int((i + 1) / total_items * 100)
            self.set_progress(progress)
            
            # Update description
            self.set_description(f"Processing item {i + 1}/{total_items}")
            
            # Do work
            process_item(i)
        
        # Mark as completed
        self.set_mcp_result({"processed": total_items})
```

### Progress Tracking Methods

- **`set_progress(progress: int)`**: Set progress percentage (0-100, automatically clamped)
- **`set_description(description: str)`**: Set human-readable description (max 1024 chars)
- **`set_status(status: str)`**: Set job status (pending, running, completed, failed, stopped)

### Progress in CommandExecutionJob

`CommandExecutionJob` supports automatic progress tracking for commands with `duration` and `steps` parameters:

```python
# Command with progress tracking
result = await execute_command("analyze_project", {
    "root_dir": "/path/to/project",
    "duration": 60,  # Expected duration in seconds
    "steps": 10,     # Number of progress updates
})
```

The job will automatically update progress based on elapsed time.

## Error Handling

### Error States

Jobs can report errors using:

```python
self.set_mcp_error("Error message", status="failed")
```

This:
- Sets job status to `FAILED`
- Stores error message in job result
- Updates description with error message

### Exception Handling

Exceptions in job `run()` method are automatically caught by `queuemgr`:
- Exception message is stored in job result
- Status is set to `FAILED`
- Stack trace is logged

### Timeout Handling

- Job execution timeouts are handled by `queuemgr`
- Timeout errors are stored in job result
- Status is set to `FAILED` or `STOPPED`

## Configuration Options

### In-Memory vs Persistent Storage

**In-Memory (default):**
- Uses temporary file that is deleted on shutdown
- Suitable for development and testing
- Jobs are lost on server restart

**Persistent Storage:**
```json
{
  "queue_manager": {
    "in_memory": false,
    "registry_path": "/var/lib/code-analysis/queue_registry.jsonl"
  }
}
```
- Jobs survive server restarts
- Suitable for production
- Requires proper file permissions

### Queue Limits

**Global Limit:**
```json
{
  "queue_manager": {
    "max_queue_size": 100
  }
}
```
- Maximum number of non-completed jobs
- When limit is reached, oldest non-completed job is deleted before adding new one
- Completed jobs are preserved until retention period expires

**Per-Type Limits:**
```json
{
  "queue_manager": {
    "per_job_type_limits": {
      "analyze_project": 3,
      "semantic_search": 10
    }
  }
}
```
- Limits number of jobs per job type
- Useful for preventing resource exhaustion
- Oldest job of that type is deleted when limit is reached

### Concurrent Jobs

```json
{
  "queue_manager": {
    "max_concurrent_jobs": 5
  }
}
```
- Maximum number of jobs running simultaneously
- Prevents system overload
- Additional jobs wait in `PENDING` status

## Best Practices

### 1. Use Queue for Long-Running Commands

```python
class AnalyzeProjectCommand(Command):
    use_queue = True  # ✅ For long-running operations
    
class SearchClassesCommand(Command):
    use_queue = False  # ✅ For fast operations (< 30 seconds)
```

### 2. Update Progress Regularly

```python
def run(self):
    items = self.mcp_params.get("items", [])
    total = len(items)
    
    for i, item in enumerate(items):
        # Update progress every 10%
        if i % (total // 10) == 0:
            progress = int((i / total) * 100)
            self.set_progress(progress)
            self.set_description(f"Processing {i}/{total} items")
        
        process_item(item)
```

### 3. Handle Errors Gracefully

```python
def run(self):
    try:
        result = perform_operation()
        self.set_mcp_result(result)
    except SpecificError as e:
        self.set_mcp_error(f"Operation failed: {str(e)}", status="failed")
    except Exception as e:
        self.logger.exception(f"Unexpected error: {e}")
        self.set_mcp_error(f"Unexpected error: {str(e)}", status="failed")
```

### 4. Use Descriptive Job Descriptions

```python
self.set_description("Analyzing project structure...")
# Later:
self.set_description("Processing Python files (45/100)...")
# Finally:
self.set_description("Generating semantic embeddings...")
```

### 5. Set Appropriate Retention Period

```json
{
  "queue_manager": {
    "completed_job_retention_seconds": 21600  // 6 hours for analysis jobs
  }
}
```

For jobs that produce important results, consider longer retention or external storage.

### 6. Monitor Queue Health

```python
health = await queue_manager.get_queue_health()
if health["failed_jobs"] > 10:
    logger.warning("High number of failed jobs detected")
```

## Examples

### Example 1: Long-Running Analysis Command

```python
from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import SuccessResult

class AnalyzeProjectCommand(Command):
    name = "analyze_project"
    use_queue = True
    descr = "Analyze Python project and generate code map"
    
    async def execute(self, root_dir: str, force: bool = False, **kwargs):
        # This will be executed in CommandExecutionJob
        # Progress updates should be done via set_progress() in the actual implementation
        result = await analyze_project_impl(root_dir, force)
        return SuccessResult(data=result)
```

### Example 2: Custom Queue Job

```python
from mcp_proxy_adapter.integrations.queuemgr_integration import QueueJobBase

class DataProcessingJob(QueueJobBase):
    def run(self):
        data = self.mcp_params.get("data", [])
        total = len(data)
        
        self.set_status("running")
        self.set_description(f"Processing {total} items...")
        
        results = []
        for i, item in enumerate(data):
            # Update progress
            progress = int((i + 1) / total * 100)
            self.set_progress(progress)
            self.set_description(f"Processing item {i + 1}/{total}")
            
            # Process item
            result = process_item(item)
            results.append(result)
        
        # Store result
        self.set_mcp_result({
            "processed": len(results),
            "results": results,
            "status": "completed"
        })
```

### Example 3: Adding Custom Job to Queue

```python
from mcp_proxy_adapter.integrations.queuemgr_integration import get_global_queue_manager
import uuid

async def process_data_async(data: list):
    queue_manager = await get_global_queue_manager()
    job_id = str(uuid.uuid4())
    
    await queue_manager.add_job(
        job_class=DataProcessingJob,
        job_id=job_id,
        params={"data": data}
    )
    
    await queue_manager.start_job(job_id)
    
    return job_id
```

### Example 4: Polling Job Status

```python
async def wait_for_job_completion(job_id: str, timeout: int = 300):
    queue_manager = await get_global_queue_manager()
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        status = await queue_manager.get_job_status(job_id)
        
        if status.status == "completed":
            return status.result
        elif status.status == "failed":
            raise Exception(f"Job failed: {status.error}")
        
        await asyncio.sleep(1)  # Poll every second
    
    raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")
```

## Built-in Queue Commands

The queue manager automatically registers these commands:

1. **`queue_add_job`**: Add a job to the queue
2. **`queue_start_job`**: Start a pending job
3. **`queue_stop_job`**: Stop a running job
4. **`queue_delete_job`**: Delete a job from the queue
5. **`queue_get_job_status`**: Get job status and result
6. **`queue_get_job_logs`**: Get job stdout/stderr logs
7. **`queue_list_jobs`**: List all jobs in the queue
8. **`queue_health`**: Get queue system health

These commands are automatically available via JSON-RPC API.

## Spawn Mode Compatibility

The queue manager uses `multiprocessing` with `spawn` mode for CUDA compatibility:

- Jobs run in separate processes
- All job classes must be picklable
- Module imports are handled automatically via `auto_import_modules`
- Logger is recreated in child process to avoid serialization issues

## Summary

The queue manager provides a robust, production-ready system for executing long-running commands asynchronously. Key features:

- ✅ Automatic job management and tracking
- ✅ Progress updates and status monitoring
- ✅ Error handling and logging
- ✅ Configurable limits and retention
- ✅ Spawn mode compatibility for CUDA
- ✅ Built-in queue management commands
- ✅ Health monitoring and diagnostics

Use `use_queue=True` for commands that take longer than 30 seconds or may block the main event loop.
