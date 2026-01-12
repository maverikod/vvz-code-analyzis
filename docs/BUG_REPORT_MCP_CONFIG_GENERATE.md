# Bug Report: mcp-config-generate command error

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-01-12  
**Component**: mcp-proxy-adapter CLI  
**Command**: `mcp-config-generate`

## Summary

The `mcp-config-generate` command fails with `TypeError` when attempting to generate configuration files. The error occurs because the CLI code passes parameters that are not accepted by the `SimpleConfigGenerator.generate()` method.

## Error Details

### Error Message
```
❌ Error generating configuration: SimpleConfigGenerator.generate() got an unexpected keyword argument 'client_enabled'
TypeError: SimpleConfigGenerator.generate() got an unexpected keyword argument 'client_enabled'
```

### Command That Triggers the Error
```bash
mcp-config-generate --protocol http --output config.json --server-port 16000 --server-host 0.0.0.0 --queue-enabled --queue-in-memory
```

## Root Cause

**File**: `.venv/lib/python3.12/site-packages/mcp_proxy_adapter/core/config/cli_generator.py`  
**Line**: 368

The CLI generator code passes `client_enabled` and other client-related parameters to `SimpleConfigGenerator.generate()`:

```python
generator.generate(
    protocol=args.protocol,
    with_proxy=args.with_proxy,
    out_path=args.output,
    # ... other parameters ...
    client_enabled=args.client_enabled,  # ❌ This parameter is not accepted
    client_protocol=args.client_protocol,
    client_cert_file=args.client_cert,
    client_key_file=args.client_key,
    client_ca_cert_file=args.client_ca,
    client_crl_file=args.client_crl,
    # ...
)
```

However, the `SimpleConfigGenerator.generate()` method signature does not include these parameters:

```python
# From simple_config_generator.py
class SimpleConfigGenerator:
    def generate(
        self,
        protocol: str,
        with_proxy: bool = False,
        out_path: str = "config.json",
        # Server parameters
        server_host: Optional[str] = None,
        server_port: Optional[int] = None,
        # ... server parameters ...
        # Registration parameters
        registration_host: Optional[str] = None,
        # ... registration parameters ...
        instance_uuid: Optional[str] = None,
    ) -> str:
        # No client_enabled, client_protocol, etc. parameters!
```

## Impact

- **Severity**: High - Command is completely unusable  
- **Affected Users**: Anyone trying to use `mcp-config-generate` CLI command  
- **Workaround**: Use Python API directly (SimpleConfigGenerator) or create config manually

## Steps to Reproduce

1. Install mcp-proxy-adapter package (version 6.9.104)
2. Run: `mcp-config-generate --protocol http --output config.json --server-port 16000 --server-host 0.0.0.0 --queue-enabled --queue-in-memory`
3. Observe TypeError about `client_enabled` parameter

## Expected Behavior

The command should generate a configuration file successfully without errors.

## Actual Behavior

The command fails with `TypeError` before generating any configuration.

## Proposed Fix

**Option 1**: Remove client-related parameters from the `generate()` call in `cli_generator.py` (lines 368-373), as they are not used by the generator.

**Option 2**: Add client-related parameters to `SimpleConfigGenerator.generate()` method signature if client configuration is needed.

**Recommended**: Option 1, since `ClientConfig` is always set to `enabled=False` in the generator code (line 127 of `simple_config_generator.py`).

### Code Fix

In `mcp_proxy_adapter/core/config/cli_generator.py`, remove lines 368-373:

```python
# REMOVE these lines:
client_enabled=args.client_enabled,
client_protocol=args.client_protocol,
client_cert_file=args.client_cert,
client_key_file=args.client_key,
client_ca_cert_file=args.client_ca,
client_crl_file=args.client_crl,
```

## Environment

- **Package**: mcp-proxy-adapter  
- **Version**: 6.9.104 (from pip list)  
- **Python Version**: 3.12  
- **OS**: Linux (6.8.0-90-generic)

## Additional Notes

1. The CLI command `mcp-config-generate` accepts `--client-enabled`, `--client-protocol`, and other client-related flags, but these cannot be processed because the underlying generator does not support them. This creates a mismatch between CLI interface and implementation.

2. The `SimpleConfigGenerator` always creates `ClientConfig(enabled=False)` regardless of any client parameters, so these parameters are effectively ignored even if they were supported.

3. There is an alternative CLI command in `mcp_proxy_adapter/cli/commands/config_generate.py` that does not have this issue, but it uses a different interface.

## Related Files

- `mcp_proxy_adapter/core/config/cli_generator.py` - Contains the bug
- `mcp_proxy_adapter/core/config/simple_config_generator.py` - Method definition
- `mcp_proxy_adapter/cli/commands/config_generate.py` - Alternative implementation (works correctly)
