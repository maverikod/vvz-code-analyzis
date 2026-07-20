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

### Queued commands are handled automatically

Every entry point — `call`, `call_validated`, `client.commands.<name>`, and the
`file_sessions` / `universal_files` facades built on `call_validated` — routes
through one queue-aware core. If the server's immediate response is a queued-job
envelope (either deployed shape: `poll_with`/`store: "queuemgr"`, or
`queued_after_timeout`), the client polls `queue_get_job_status` for you until
the job reaches a terminal state, then returns the unwrapped inner result — the
same shape you'd get from a synchronous call. You never see the raw envelope.

```python
# No special handling needed: queued or not, this returns the real result.
out = await client.call("some_long_running_command", {...})
```

Failures raise instead of returning an error envelope:

* `CommandFailedError` — the job completed but the command itself failed
  (`inner result {"success": false}` / `command_success is False` /
  `completed_with_error`). Carries `.command`, `.job_id`, `.error`.
* `JobFailedError` — the job failed/stopped/cancelled, or reported `error`.
  Carries `.job_id`, `.error`, `.status`.
* `JobTimeoutError` — only raised when you pass an explicit `timeout` and it
  elapses; the job keeps running server-side. By default (`timeout=None`) the
  client polls until the job finishes, however long that takes.

Optional keyword args on `call` / `call_validated` (and their `call_unified*`
counterparts): `timeout` (seconds, default `None` = wait until terminal),
`poll_interval` (seconds between polls, default `1.0`), `status_hook` (sync or
async callable invoked with each poll's status dict).

`call_unified` / `call_unified_validated` are kept as **deprecated aliases** of
`call` / `call_validated` for backward compatibility — `expect_queue` and
`auto_poll` are accepted but ignored, since queue handling is now always on.
Prefer `call` / `call_validated` directly.

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

Pass `refresh_schema=True` on a single call to bypass the in-memory schema cache.

## High-level facades (aligned with live server registry)

The client does **not** wrap CST commands (`cst_load_file`, …) or legacy file I/O
(`universal_file_read`, `read_project_text_file`, …). Those commands are removed
from the server registry. Use the facades below or generic `call` / `commands.*`.

| Facade | Property | Server commands |
|--------|----------|-----------------|
| Client DB sessions + transfer | `client.file_sessions` | `session_*`, `subordinate_session_*`, `project_file_transfer_*`, `project_file_advisory_lock_batch` |
| Universal file preview | `client.universal_files` | `universal_file_preview` (read-only) |
| Any registered command | `client.call` / `client.commands.<name>` | schema from live `help()` |

Canonical command lists: `code_analysis_client.server_api` — exported as
`FILE_SESSION_COMMANDS`, `FILE_SESSION_FACADE_METHODS`, `CLIENT_FACADE_COMMANDS`,
`REMOVED_COMMANDS`.

**Scope boundary:** this client manipulates files only as whole units — transfer,
locks, sessions, and structured read-only preview — and analyzes them. Content
editing (open/edit/write/close draft sessions) is not served by this project's
code-analysis server; use the ai-editor client for that.

Sync checks (in-process registry):

```bash
pytest tests/test_client_server_api_sync.py tests/test_code_analysis_client.py -k session
```

Package version is in the root ``pyproject.toml``; before a client wheel build run
``python scripts/sync_code_analysis_client_version.py`` (also done by ``release_build.sh``).

## Examples (this repository)

Runnable scripts live under `client/examples/`. **Long-form “man page” style
documentation** is embedded in the **module docstrings** of those Python files
(see `client/examples/README.md` for how to read them).

| Script | Purpose |
|--------|---------|
| `run_all_examples.py` | Full API tour + runs all live sibling scripts |
| `ex_minimal_validated.py` | Smallest validated RPC example |
| `ex_universal_files.py` | `UniversalFileClient.preview` (read-only structured preview) |
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
