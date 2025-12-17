# Docker Network Configuration

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Overview

The code-analysis-server is configured to work in Docker network `smart-assistant`. The server binds to `0.0.0.0` to listen on all interfaces, but uses the Docker network gateway IP address for communication with the proxy running in containers.

## Network Configuration

### Server Binding

- **host**: `0.0.0.0` - Server listens on all network interfaces
- **advertised_host**: `172.28.0.1` - Gateway IP in smart-assistant network (used by proxy in containers)

### Registration URLs

- **register_url**: `https://172.28.0.1:3005/register`
- **unregister_url**: `https://172.28.0.1:3005/unregister`
- **heartbeat_url**: `https://172.28.0.1:3005/proxy/heartbeat`

## Automatic Detection

The configuration generator automatically detects the Docker network gateway IP:

1. **Environment Variables**: Checks `DOCKER_HOST_IP` or `SMART_ASSISTANT_HOST_IP`
2. **Docker Network**: Queries `docker network inspect smart-assistant` for gateway IP
3. **Fallback**: Uses host IP address from `hostname -I` or `socket.gethostbyname()`

## Manual Configuration

You can override the host IP using environment variables:

```bash
export DOCKER_HOST_IP=172.28.0.1
python -m code_analysis.cli.config_cli generate --protocol mtls --out config.json
```

Or specify directly in CLI:

```bash
python -m code_analysis.cli.config_cli generate \
    --protocol mtls \
    --out config.json \
    --server-host 0.0.0.0 \
    --registration-host 172.28.0.1
```

## Why 0.0.0.0?

Binding to `0.0.0.0` allows the server to:
- Accept connections from localhost
- Accept connections from Docker containers
- Accept connections from other network interfaces

The `advertised_host` tells the proxy where to connect, while `host: 0.0.0.0` ensures the server listens on all interfaces.

## Network Topology

```
Host Machine (172.28.0.1 - gateway)
    │
    ├── code-analysis-server (listening on 0.0.0.0:15000)
    │
    └── Docker Network: smart-assistant
        │
        └── mcp-proxy (container)
            └── Connects to 172.28.0.1:15000
```

## Troubleshooting

### Server not reachable from container

1. Check that server is bound to `0.0.0.0`, not `127.0.0.1`
2. Verify gateway IP is correct: `docker network inspect smart-assistant`
3. Check firewall rules allow connections on port 15000
4. Verify `advertised_host` matches gateway IP

### Registration fails

1. Ensure registration URLs use gateway IP, not `localhost`
2. Check that proxy is accessible at gateway IP:3005
3. Verify mTLS certificates are valid for gateway IP
