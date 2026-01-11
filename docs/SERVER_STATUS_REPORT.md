# Server Status Report

**Generated**: 2026-01-11 09:28  
**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com

## Executive Summary

Server was successfully restarted after database cleanup. Schema synchronization completed successfully. File watcher is actively scanning projects and processing files. Database worker is running and handling requests.

## Database Status

### Schema
- **Version**: 1.0.0 ✅
- **Status**: Synchronized successfully
- **Tables**: 23 tables created
- **Size**: 2.05 MB (growing)

### Data Statistics
- **Projects**: 4 projects registered
  - test_project_20260109
  - bhlff
  - test_new_project
  - vast_srv
- **Files**: 25 total files
  - Active: 25
  - Deleted: 0
  - Needing chunking: 16
- **Chunks**: 0 chunks
  - Vectorized: 0
  - Not vectorized: 0

### Recent Activity
- Files updated in last 24h: 25
- Schema sync completed: ✅
- Database created: 2026-01-11 09:25

## Worker Status

### DB Worker
- **Status**: ✅ Running
- **PID**: 23315
- **Socket**: `/tmp/code_analysis_db_workers/code_analysis.sock`
- **Last Activity**: Active (handling requests from file watcher)
- **Log**: `logs/db_worker.log` (last entry: 2026-01-10 21:08 - shutdown signal)

### File Watcher
- **Status**: ✅ Running
- **Activity**: Actively scanning and processing files
- **Last Scan**: 2026-01-11 09:25:24
- **Scan Results**: 
  - Files scanned: 1502
  - Projects: 4
  - Delta: new=1495, changed=0, deleted=0
  - Duration: 7.75s
- **Log**: `logs/file_watcher.log` (active)

### Vectorization Worker
- **Status**: ⚠️ Not running (no active process)
- **Last Activity**: 2026-01-10 15:24
- **Log**: `logs/vectorization_worker.log` (7.7 MB)

## Server Process

- **Main Process**: ✅ Running
- **PID**: 23240, 23315, 23317, 23319, 23324
- **Command**: `python -m code_analysis.main --config config.json --daemon`
- **Started**: 2026-01-11 09:25
- **Uptime**: ~3 minutes

## Issues and Warnings

### Errors Detected

1. **FOREIGN KEY constraint failed** (2026-01-11 09:25:23)
   - Project: b08deff6-2c47-49d1-93bf-9fae0b77db30
   - Issue: Failed to create dataset due to missing project reference
   - Impact: Project not fully registered in database

2. **Project ID mismatch** (2026-01-11 09:25:16)
   - File: `/home/vasilyvz/projects/tools/code_analysis/test_data/test_new_project/test_file.py`
   - Issue: Project ID in projectid file doesn't match database project ID
   - Impact: File not analyzed

3. **Auto-indexing failure** (2026-01-11 09:25:16)
   - Project: 928bcf10-db1c-47a3-8341-f60a6d997fe7
   - Issue: 'SuccessResult' object has no attribute 'success'
   - Impact: Auto-indexing for new project failed

### Warnings

- Vectorization worker not running - chunks will not be vectorized
- Some projects have data integrity issues (FOREIGN KEY constraints)

## Actions Taken

1. ✅ Database file deleted and recreated
2. ✅ Versions directory cleaned
3. ✅ Server restarted
4. ✅ Schema synchronized (version 1.0.0)
5. ✅ File watcher started scanning projects
6. ✅ DB worker started and handling requests

## Recommendations

1. **Fix project data integrity**:
   - Check project b08deff6-2c47-49d1-93bf-9fae0b77db30
   - Verify project IDs match between projectid files and database

2. **Start vectorization worker**:
   - 16 files need chunking
   - 0 chunks need vectorization (after chunking)
   - Worker should be started to process pending work

3. **Monitor file watcher**:
   - Currently processing files actively
   - Monitor for any additional errors

4. **Review auto-indexing**:
   - Fix SuccessResult attribute error
   - Ensure new projects are properly indexed

## Log Files

- Server startup: `/tmp/server_startup.log`
- DB worker: `logs/db_worker.log`
- File watcher: `logs/file_watcher.log`
- Vectorization worker: `logs/vectorization_worker.log`
