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

## High-level facades (aligned with live server registry)

The client does **not** wrap CST commands (`cst_load_file`, …) or legacy file I/O
(`universal_file_read`, `read_project_text_file`, …). Those commands are removed
from the server registry. Use the facades below or generic `call` / `commands.*`.

| Facade | Property | Server commands |
|--------|----------|-----------------|
| Client DB sessions + transfer | `client.file_sessions` | `session_*`, `subordinate_session_*`, `project_file_transfer_*`, `project_file_advisory_lock_batch` |
| Universal edit sessions | `client.universal_files` | `universal_file_open`, `edit`, `write`, `close`, `preview` |
| Any registered command | `client.call` / `client.commands.<name>` | schema from live `help()` |

Canonical command lists: `code_analysis_client.server_api` — exported as
`FILE_SESSION_COMMANDS`, `FILE_SESSION_FACADE_METHODS`, `CLIENT_FACADE_COMMANDS`,
`REMOVED_COMMANDS`.

Sync checks (in-process registry):

```bash
pytest tests/test_client_server_api_sync.py tests/test_code_analysis_client.py -k session
```

Package version is in ``client/code_analysis_client/version.txt`` (synced with the
root ``code-analysis`` project via ``scripts/sync_code_analysis_client_version.py``).

## Examples (this repository)

Runnable scripts live under `client/examples/`. **Long-form “man page” style
documentation** is embedded in the **module docstrings** of those Python files
(see `client/examples/README.md` for how to read them).

| Script | Purpose |
|--------|---------|
| `run_all_examples.py` | Full API tour + runs all live sibling scripts |
| `ex_minimal_validated.py` | Smallest validated RPC example |
| `ex_universal_files.py` | All `UniversalFileClient` methods (open/edit/write/close/preview) |
| `ex_session_view_subordinates.py` | `session_view` and subordinate CRUD |
| `ex_file_sessions.py` | Sessions, locks, transfer roundtrip |
| `ex_config_only.py` | Parse `config.json` without TCP |

```bash
casmgr --config config.json start
python client/examples/run_all_examples.py
```

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
