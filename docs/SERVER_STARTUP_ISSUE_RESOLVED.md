# Server Startup Issue Resolution

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-29

## Problem Summary

Server was failing to start properly - port 15000 was not listening, preventing OpenAPI schema access and API calls.

## Root Cause

The issue was in the registration patch (`code_analysis/core/registration_patch.py`):

1. **Error**: `'RegistrationContext' object has no attribute 'get'`
   - The patch was trying to use `config.get("registration", {})` 
   - But `config` parameter could be a `RegistrationContext` object, not a dictionary
   - `RegistrationContext` is an object with attributes, not a dict with `.get()` method

2. **Impact**: 
   - Registration attempts failed with `AttributeError`
   - Server couldn't complete startup sequence
   - Port 15000 never started listening
   - Multiple server processes were spawned (failed restarts)

## Solution

Fixed the patch to handle both dictionary and object types:

```python
# Before (broken):
self._proxy_registration_config = config.get("registration", {})

# After (fixed):
if isinstance(config, dict):
    self._proxy_registration_config = config.get("registration", {})
else:
    # If config is RegistrationContext or other object, use stored config
    self._proxy_registration_config = getattr(self, '_proxy_registration_config', {}) or getattr(context, 'registration_config', {})
```

## Verification

After fix:
- ✅ Port 15000 is now listening: `tcp 0 0 172.28.0.1:15000 0.0.0.0:* LISTEN`
- ✅ Server process running: PID 269278
- ✅ OpenAPI schema accessible via mTLS
- ✅ Health endpoint responding

## Status

**RESOLVED** - Server now starts successfully and listens on port 15000.

## Notes

- Registration with proxy may still show "already registered" errors, but this is handled by the patch (unregister + re-register)
- Server is functional even if proxy registration has issues
- Multiple server processes issue resolved - old processes were killed before restart

