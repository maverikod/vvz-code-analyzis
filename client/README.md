# code-analysis-client

Async Python client for the **code-analysis** server. It wraps `mcp-proxy-adapter`’s `JsonRpcClient`, so you get the adapter’s built-in methods (queue, transfer, `help`, `health`, …) plus thin helpers to run any registered server command.

## Install

```bash
pip install code-analysis-client
```

## Usage

```python
import asyncio
from code_analysis_client import CodeAnalysisAsyncClient


async def main() -> None:
    client = CodeAnalysisAsyncClient(
        protocol="https",
        host="127.0.0.1",
        port=15001,
        cert="/path/client.crt",
        key="/path/client.key",
        ca="/path/ca.crt",
        timeout=120.0,
    )
    async with client:
        h = await client.rpc.help()
        r = await client.call("list_projects", {"include_deleted": False})
    print(h, r)


asyncio.run(main())
```

Build client settings from the same JSON shape as the pipeline adapter settings (`host`, `port`, `protocol`, optional `ssl` with `cert` / `key` / `ca` or `*_path` aliases), or from a full server `config.json` object.

```python
from code_analysis_client import CodeAnalysisAsyncClient

client = CodeAnalysisAsyncClient.from_server_config(config_dict, timeout=60.0)
```

Queued/long commands: use `client.call_unified(..., expect_queue=True, auto_poll=True)` or the underlying `client.rpc.execute_command_unified(...)`.

## Validation using the server schema

The authoritative input schema is whatever the running server returns from **`help`** with `cmdname` set to the command. The client calls that, optionally caches the result, performs the same shallow checks as the server’s `BaseMCPCommand` (types, `required`, `enum`, `additionalProperties`), then runs the command.

```python
async with CodeAnalysisAsyncClient(host="127.0.0.1", port=15001) as client:
    # Explicit
    out = await client.call_validated(
        "list_projects",
        {"include_deleted": False},
    )
    # Dynamic wrapper: same as call_validated("list_projects", {...})
    out = await client.commands.list_projects(include_deleted=False)
    # After server reload
    client.clear_command_schema_cache()
```

Use `call_unified_validated` when you need queue polling. Pass `refresh_schema=True` on a single call to bypass the in-memory schema cache.

## Examples (this repository)

Runnable scripts live under `client/examples/`. **Long-form “man page” style
documentation** is embedded in the **module docstrings** of those Python files
(see `client/examples/README.md` for how to read them). Full API walkthrough:
`python client/examples/run_all_examples.py` with the daemon up and
`CODE_ANALYSIS_CONFIG` or default `config.json` at the repo root.

## Development

From the repository root:

```bash
pip install -e ./client
pytest tests/test_code_analysis_client.py
```

### Releasing to PyPI (version = root ``code-analysis`` project)

The client wheel version is read from ``client/code_analysis_client/version.txt``.
That file must match ``[project].version`` in the **repository root**
``pyproject.toml``. Sync before build:

```bash
python scripts/sync_code_analysis_client_version.py
cd client && python -m build && twine check dist/* && twine upload dist/*
```
