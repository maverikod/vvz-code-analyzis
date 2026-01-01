# Bug Report: Registration Manager - "Already Registered" Error Handling

**Author:** Vasiliy Zdanovskiy  
**Email:** vasilyvz@gmail.com  
**Date:** 2025-12-31  
**Package:** `mcp_proxy_adapter`  
**Component:** `api.core.registration_manager.manager.RegistrationManager`  
**Status:** 🔴 **CONFIRMED BUG** - Requires fix in adapter or workaround in application code

## Summary

When a server is already registered with the proxy, the `RegistrationManager.register_with_proxy()` method attempts to unregister and reset status, but **returns `False`**, causing registration to fail and trigger retry loops. The adapter should automatically unregister the old registration and re-register, returning `True` on success.

## Problem Description

### Current Behavior

When a server tries to register but receives an error that it's "already registered", the current implementation:

1. Logs a warning: `"⚠️  Server already registered, unregistering and resetting status"`
2. Sets `self.registered = False`
3. Calls `await set_registration_status(False)`
4. Attempts to unregister: `await self.unregister()`
5. Returns `False` (registration failed)

This causes:
- Unnecessary unregistration attempts
- Status set to "not registered" even though server IS registered
- Potential disruption to existing heartbeat
- Multiple retry attempts that will fail

### Expected Behavior

When server is already registered:

1. Extract `server_key` from error message (e.g., "code-analysis-server_1")
2. Log info: `"✅ Server already registered as {server_key}, setting status to registered and continuing with heartbeat"`
3. Set `self.registered = True`
4. Call `await set_registration_status(True)`
5. Return `True` (success)
6. Continue with normal heartbeat operation

## Reproduction Steps

1. Start a server with registration enabled
2. Server successfully registers with proxy
3. Restart the server (or start another instance with same URL)
4. Server attempts to register again
5. Proxy returns error: `"Server with URL https://172.28.0.1:15000 is already registered as code-analysis-server_1"`
6. Server logs error and attempts to unregister
7. Server retries registration multiple times

## Error Messages

From logs:
```
2025-12-29 01:16:48 - mcp_proxy_adapter - ERROR - 🔍 [REG_MANAGER] ❌ Exception in register_with_proxy: ConnectionError: HTTP error connecting to https://172.28.0.2:3004/register: Registration failed: Server with URL https://172.28.0.1:15000 is already registered as code-analysis-server_1
```

## Code Location

**File:** `.venv/lib/python3.12/site-packages/mcp_proxy_adapter/api/core/registration_manager/manager.py`

### Location 1: Direct error message check (Lines 216-226)

```python
if "already registered" in error_msg:
    self.logger.warning(
        "⚠️  Server already registered, unregistering and resetting status"
    )
    self.registered = False
    await set_registration_status(False)
    await set_registration_snapshot(registered=False)
    try:
        await self.unregister()
    except Exception as e:
        self.logger.warning(f"Failed to unregister: {e}")
    return False  # ❌ BUG: Returns False, causing retry loop
```

### Location 2: Exception handler (Lines 246-260)

**Проблема:** При обработке исключения `ConnectionError` с сообщением "already registered" код не проверяет это условие и просто повторяет попытку регистрации, что приводит к бесконечному циклу повторных попыток.

```python
except Exception as exc:  # noqa: BLE001
    full_error = self._format_httpx_error(exc)
    # ❌ BUG: No check for "already registered" in exception handler
    if attempt < max_retries - 1:
        self.logger.warning(
            "⚠️  Registration attempt %s/%s failed: %s. Retrying in %ss...",
            attempt + 1,
            max_retries,
            full_error,
            retry_delay,
        )
        await asyncio.sleep(retry_delay)
    else:
        # ... error logging ...
        raise
```

**Проблема:** Когда `ConnectionError` содержит "already registered", исключение обрабатывается как обычная ошибка и происходит повторная попытка, что приводит к бесконечному циклу.

## Proposed Fix

### Option 1: Handle in `register_with_proxy` method

Modify the error handling in `RegistrationManager.register_with_proxy()`:

```python
if "already registered" in error_msg:
    # Extract server_key from error message
    import re
    match = re.search(r"already registered as ([^\s,]+)", error_msg)
    if match:
        server_key = match.group(1)
        self.logger.info(
            f"✅ Server already registered as {server_key}, "
            "setting status to registered and continuing with heartbeat"
        )
        self.registered = True
        await set_registration_status(True)
        return True
    else:
        # Fallback if server_key cannot be extracted
        self.logger.info(
            "✅ Server already registered, setting status to registered and continuing with heartbeat"
        )
        self.registered = True
        await set_registration_status(True)
        return True
```

### Option 2: Handle in exception handler (КРИТИЧНО)

**Обязательно** нужно обработать "already registered" в обработчике исключений (lines 246-260), так как ошибка приходит как `ConnectionError`:

```python
except Exception as exc:  # noqa: BLE001
    full_error = self._format_httpx_error(exc)
    
    # ✅ КРИТИЧНО: Проверка "already registered" в исключении
    if "already registered" in full_error.lower():
        # Extract server_key from error message
        import re
        match = re.search(r"already registered as ([^\s,]+)", full_error.lower())
        server_key = match.group(1) if match else "unknown"
        
        self.logger.info(
            f"🔄 Server already registered as {server_key}, "
            "unregistering and re-registering..."
        )
        
        # Unregister old registration
        try:
            await self.unregister()
            self.logger.info(f"✅ Unregistered {server_key}")
        except Exception as unreg_exc:
            self.logger.warning(f"⚠️  Failed to unregister: {unreg_exc}")
        
        # Wait for proxy to process unregistration
        await asyncio.sleep(1.0)
        
        # Re-register
        try:
            registration_response = await _register()
            if registration_response and registration_response.get("success"):
                self.logger.info(f"✅ Successfully re-registered after auto-fix")
                self.registered = True
                await set_registration_status(True)
                await set_registration_snapshot(registered=True)
                return True
            else:
                self.logger.error("❌ Re-registration failed after unregister")
                # Fall through to retry logic
        except Exception as rereg_exc:
            self.logger.error(f"❌ Re-registration exception: {rereg_exc}")
            # Fall through to retry logic
    
    # Existing retry logic for other errors
    if attempt < max_retries - 1:
        self.logger.warning(
            "⚠️  Registration attempt %s/%s failed: %s. Retrying in %ss...",
            attempt + 1,
            max_retries,
            full_error,
            retry_delay,
        )
        await asyncio.sleep(retry_delay)
    else:
        # ... existing error logging ...
        raise
```

### Option 3: Handle in `JsonRpcClient.register_with_proxy`

Also check in `.venv/lib/python3.12/site-packages/mcp_proxy_adapter/client/jsonrpc_client/proxy_api.py` at lines 196-211:

```python
if response.status_code == 400:
    error_data = cast(Dict[str, Any], response.json())
    error_msg = error_data.get("error", "").lower()
    if "already registered" in error_msg:
        # Instead of retrying after unregister, return success
        import re
        match = re.search(r"already registered as ([^\s,]+)", error_msg)
        if match:
            server_key = match.group(1)
            # Return mock success response
            return {
                "success": True,
                "server_key": server_key,
                "server_url": server_url,
                "message": f"Server already registered as {server_key}",
            }
```

## Impact

### Current Impact
- **Severity:** Medium
- **Frequency:** Every server restart when server is already registered
- **User Impact:** 
  - Unnecessary error logs
  - Potential disruption to heartbeat
  - Multiple failed registration attempts
  - Confusing error messages

### After Fix
- Server gracefully handles "already registered" case
- Status correctly set to "registered"
- Heartbeat continues normally
- No unnecessary unregistration attempts
- Cleaner logs

## Additional Context

### Related Code

1. **RegistrationManager.register_with_proxy()** - Main registration method
2. **JsonRpcClient.register_with_proxy()** - Client-side registration
3. **RegistrationManager.start_heartbeat()** - Heartbeat task (should continue normally)

### Error Message Format

Proxy returns error in format:
```json
{
  "success": false,
  "error": "Server with URL https://172.28.0.1:15000 is already registered as code-analysis-server_1",
  "error_code": "REGISTRATION_ERROR"
}
```

The `server_key` (e.g., "code-analysis-server_1") can be extracted using regex: `r"already registered as ([^\s,]+)"`

## Test Cases

1. **Test: Server restart with existing registration**
   - Start server (registers successfully)
   - Restart server
   - Verify: Status set to "registered", heartbeat continues

2. **Test: Multiple instances with same URL**
   - Start server instance 1 (registers successfully)
   - Start server instance 2 (should handle "already registered" gracefully)
   - Verify: Instance 2 sets status to "registered" and continues

3. **Test: Server_key extraction**
   - Verify regex correctly extracts server_key from various error message formats
   - Test with different server_key formats

## Recommendations

1. **КРИТИЧНО - Immediate Fix:** 
   - **Обязательно** исправить Option 2 (обработка исключения) - это основная проблема
   - Опционально исправить Option 1 (прямая проверка error_msg) для улучшения логирования
   - При обработке исключения: отменить старую регистрацию, подождать, зарегистрироваться заново, вернуть `True`

2. **Long-term:** 
   - Добавить API endpoint в proxy для проверки статуса регистрации
   - Добавить метод `check_registration_status()` в `RegistrationManager`

3. **Documentation:** 
   - Обновить документацию регистрации с объяснением обработки "already registered"
   - Добавить примеры обработки ошибок регистрации

## Related Issues

- Server restart causes registration errors
- Heartbeat may be disrupted during registration retries
- Status incorrectly shows "not registered" when server IS registered

---

**Priority:** Medium  
**Status:** Open  
**Assigned To:** mcp_proxy_adapter maintainers

