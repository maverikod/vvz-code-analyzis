# Proxy Registration — Comparative Analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Summary

- **code-analysis-server** registers successfully with the proxy at `https://172.28.0.2:3004` when it is running (HTTP 200, "Server code-analysis-server registered successfully").
- After shutdown it unregisters ("Unregistered from proxy: code-analysis-server").
- **MCP-Proxy-2** (Cursor’s proxy) returns only **svo-chunker** and **embedding-service** in `list_servers`. If Cursor’s MCP is configured to use the same proxy (172.28.0.2:3004), then code-analysis-server appears only while it is running and sending heartbeats.

## Comparison: Servers in Proxy Registry

| Aspect | svo-chunker | embedding-service | code-analysis-server |
|--------|-------------|-------------------|----------------------|
| **server_id** | svo-chunker | embedding-service | code-analysis-server |
| **server_url** | https://svo-chunker:8009 | https://172.28.0.4:8001 | https://172.28.0.1:15000 |
| **Registration** | Static/config or long-lived | Static/config or long-lived | Dynamic (register on startup, unregister on shutdown) |
| **registered_at** | 2026-02-04 | 2026-02-04 | — (removed after process exit) |
| **Network** | Docker hostname | Docker IP 172.28.0.4 | Config: 172.28.0.1 (bind 0.0.0.0 works) |

## Why code-analysis-server May Not Appear in list_servers

1. **Process not running**  
   After `pkill` or timeout the process exits, calls unregister, and is removed from the proxy registry. So when we call `list_servers` later, code-analysis-server is no longer there.

2. **Different proxy instance**  
   If Cursor’s MCP-Proxy-2 is pointed at a different proxy (e.g. localhost) than 172.28.0.2:3004, that proxy has its own registry. code-analysis-server registers only with 172.28.0.2:3004 (from config `registration.register_url`). So list_servers would show only what that other proxy has.

3. **Bind address**  
   If config has `server.host: 172.28.0.1` and that interface is missing, the server may fail to bind and exit before registering. Using `--host 0.0.0.0` allows bind and registration succeeds.

## What the Logs Show

- **Registration request:** POST to `https://172.28.0.2:3004/register` with payload `server_id`, `server_url`, `uuid`, etc.
- **Response:** 200, `"message":"Server code-analysis-server registered successfully"`.
- **Heartbeat:** Sent every 30s to `https://172.28.0.2:3004/proxy/heartbeat`, acknowledged.
- **On shutdown:** "Unregistered from proxy: code-analysis-server".

So registration and heartbeat with the proxy at 172.28.0.2:3004 work when the process is up.

## Recommendations

1. **Keep the server running** when testing via proxy: start with `--daemon` (and optionally `--host 0.0.0.0` if 172.28.0.1 is not available). Do not kill the process before calling `list_servers` / `call_server`.
2. **Confirm Cursor’s MCP proxy URL**: ensure the MCP client used by Cursor (MCP-Proxy-2) talks to the same proxy as in config (`https://172.28.0.2:3004`). If it uses another URL, either point it to 172.28.0.2:3004 or add code-analysis-server to that other proxy’s config/registry.
3. **Optional:** Add code-analysis-server to the proxy’s static config (like svo-chunker/embedding-service) so it appears even before the first registration, if the proxy supports that.

## Quick Test (when server is running)

1. Start: `python -m code_analysis.main --config config.json --daemon [--host 0.0.0.0]`
2. Wait ~30s for registration and first heartbeat.
3. Via MCP Proxy: `list_servers` → expect code-analysis-server if the proxy is 172.28.0.2:3004.
4. `call_server(server_id="code-analysis-server", command="health", params={})`.
5. `call_server(server_id="code-analysis-server", command="list_projects", params={})`, then e.g. `fulltext_search`, `search_ast_nodes` with `project_id`.

## Test Results (via MCP Proxy)

With the server running (daemon + `--host 0.0.0.0`) and registered:

- **list_servers**: code-analysis-server appears (together with svo-chunker, embedding-service).
- **health**: success; `proxy_registration.registered: true`, `proxy_url: https://172.28.0.2:3004`.
- **list_projects**: success; returns projects (e.g. cli_app).
- **fulltext_search** (project_id, query, limit): success; returns FTS5 results with entity_type, file_path, bm25_score.
- **search_ast_nodes** (project_id, node_type=ClassDef): success; returns nodes with name, file_path, line.
- **find_classes** (project_id): success; returns classes list.
- **get_worker_status** (worker_type=indexing): success; returns summary (is_running, etc.).

Conclusion: When the server process is running and registered, all tested commands work through the MCP Proxy.
