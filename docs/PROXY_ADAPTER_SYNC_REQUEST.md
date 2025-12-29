"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

## Proxy / Adapter sync request

## Status

**FIXED upstream in `mcp_proxy_adapter` (current `.venv` state).**

- `/health.components.proxy_registration` now reports status using
  `mcp_proxy_adapter.api.core.registration_manager.get_registration_snapshot_sync()`
  (single source of truth).
- `AuthManager.get_headers()` exists again, so legacy registration client no longer
  crashes with `AttributeError`.

This document is kept as historical context for what was out of sync and what was
requested from adapter/proxy developers.

## Summary

There are **two different proxy registration implementations** living in `mcp_proxy_adapter`, and they are currently **out of sync**:

- **Working path (actual registration used in production)**: `api/core/registration_manager` + `client/jsonrpc_client/proxy_api.py` (register + heartbeat).
- **Broken/legacy path (used by `/health.components.proxy_registration`)**: `core/proxy_registration.py` + `core/proxy/proxy_registration_manager.py`.

As a result:

- Server registration in MCP-Proxy **works** (confirmed by registration logs and by MCP-Proxy server list).
- Previously, `/health` could report `components.proxy_registration.enabled=false` and `registered=false`
  due to reading status from a legacy path. This is now fixed upstream.

## Evidence (code references)

- `/health` uses legacy proxy-registration status:
  - `mcp_proxy_adapter/commands/health_command.py` calls `get_proxy_registration_status()`.
  - `mcp_proxy_adapter/core/proxy_registration.py` returns `enabled=false` if `_registration_manager` is not initialized via `initialize_proxy_registration(config)`.

- Actual registration/heartbeat uses a different mechanism:
  - `mcp_proxy_adapter/api/core/registration_manager/manager.py` performs registration using `JsonRpcClient.register_with_proxy(...)` and then the heartbeat loop keeps it alive.
  - `mcp_proxy_adapter/api/core/registration_tasks.py` heartbeat loop attempts registration before sending heartbeat when `registration_manager.registered` is false.

## Evidence (runtime/logs)

On server startup, adapter logs show successful registration + heartbeat:

- `✅ Successfully registered with proxy as <server_name> -> <server_url>`
- `💓 Heartbeat/registration acknowledged by proxy`

Yet `/health` reports:

- `components.proxy_registration.enabled=false`
- `components.proxy_registration.registered=false`

This mismatch is expected given the two independent registration systems above.

## Bug 1 (fixed): `core/proxy/registration_client.py` was calling a non-existing AuthManager API

From logs (stacktrace):

- `AttributeError: 'AuthManager' object has no attribute 'get_headers'`
- Location: `mcp_proxy_adapter/core/proxy/registration_client.py` calls `headers = self.auth_manager.get_headers()`.

This indicated `RegistrationClient` and `AuthManager` implementations were not aligned. Fixed upstream.

## Bug 2: Confusing builtin command `proxy_registration`

`mcp_proxy_adapter/commands/proxy_registration_command.py` implements an **in-memory registry for testing**, but the name suggests it performs real MCP-Proxy registration.

This is confusing operationally because the real registration path is heartbeat/JsonRpcClient-based.

## Requested changes (recommended minimal plan)

### 1) Define single source of truth for registration state

Pick **one** registration subsystem:

- Recommended: `api/core/registration_manager` (it already works in production).

### 2) Fix `/health.components.proxy_registration`

Options:

- **Option A (recommended)**: Report status from `api/core/registration_manager.status` (the same status that heartbeat updates).
- Option B: Fully remove/deprecate `core/proxy_registration.py` and the legacy `ProxyRegistrationManager` path.
- Option C: Make `core/proxy_registration` a thin wrapper around `api/core/registration_manager` so status is consistent.

### 3) Remove or fix the broken legacy auth path

If `core/proxy/registration_client.py` stays:

- Either implement the missing `AuthManager.get_headers()` API (or restore it),
- Or update `RegistrationClient` to use the current `AuthManager` interface.

If the legacy path is deprecated:

- Remove it and stop referencing it from health command.

### 4) Clarify builtin `proxy_registration` command semantics

Options:

- Rename it to something explicitly test-only (e.g. `proxy_registration_mock`),
- Or implement it as a manual trigger for the real registration manager.

## Expected outcome

After synchronization:

- Registration state in `/health` matches actual MCP-Proxy registration.
- No more log spam / runtime errors from legacy `core/proxy_registration` code.
- Reduced operational confusion around `proxy_registration` command vs real registration flow.


