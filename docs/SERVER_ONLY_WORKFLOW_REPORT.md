# Server-only workflow test report

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Goal

1. Create two projects (server only)
2. Create two CLI apps in each project (server only)
3. Verify apps in console
4. Test editing via server
5. Delete projects (server only)

---

## Completed

### 1. Two projects created via server (create_project)

- **proj1**: `project_id` = `aea6ed9a-9fdd-4ef6-b1f7-4d719812f2e3`, path `test_data/proj1`
- **proj2**: `project_id` = `19adc693-eb6c-448c-ba52-2723b36cf2bb`, path `test_data/proj2`

Used: `create_project` with `root_dir`, `watch_dir_id` (550e8400-e29b-41d4-a716-446655440001), `project_name`, `description`. Server created directories and projectid files.

### 2. Two CLI apps per project created via server (cst_convert_and_save)

- **proj1**: `hello_cli.py` (greeting CLI), `calc_cli.py` (calculator CLI)
- **proj2**: `hello_cli.py`, `calc_cli.py`

Used: `cst_convert_and_save` with `project_id`, `file_path`, `source_code`, `save_to_file: true`. All four files were created on disk with correct content. (Some proxy calls returned "peer closed connection" / "server unavailable" after large responses; files were still created.)

### 3. Console verification

- `python test_data/proj1/hello_cli.py` → "Hello, World!"
- `python test_data/proj1/hello_cli.py --name User` → "Hello, User!"
- `python test_data/proj1/calc_cli.py 2 3` → 5.0
- `python test_data/proj1/calc_cli.py 10 4 --op div` → 2.5
- `python test_data/proj2/hello_cli.py --name Proj2` → "Hello, Proj2!"
- `python test_data/proj2/calc_cli.py 5 5 --op mul` → 25.0

All six runs succeeded; apps work.

---

## Blocked (server unavailable)

### 4. Editing via server

Planned: `cst_load_file` → `cst_modify_tree` (e.g. change greeting text) → `cst_save_tree`, then verify in console.

**Cause:** MCP Proxy reports "Server code-analysis-server_1 is unavailable: All connection attempts failed". Editing was not performed.

### 5. Delete projects via server

Planned: `delete_project` for each `project_id` with `delete_from_disk: true` (move to trash).

**Cause:** Same as above — proxy cannot connect to code-analysis-server. Deletion was not performed.

---

## Root cause (proxy ↔ server)

- Server is configured with `host: 172.28.0.1`, `port: 15000` (Docker bridge).
- Proxy runs in Cursor (host) and calls that address; "All connection attempts failed" suggests 172.28.0.1 is not reachable from the host or the server process is not accepting connections (e.g. after a crash or timeout on large `cst_convert_and_save` responses).
- No CLI for `delete_project` exists; deletion is only available via MCP/server.

---

## Post-restart (2026-01-29)

- **For proxy (mTLS):** Start the server **without** overriding host/port: `python -m code_analysis.main --config config.json --daemon`. The server will bind to 172.28.0.1 with mTLS and auto-register at `registration.register_url`. Do **not** use `--host 127.0.0.1` when the proxy expects the server at 172.28.0.1 with mTLS.
- **Proxy registry:** If code-analysis-server is not in the proxy's list, ensure the server is started with config as-is (no --host/--port) so it can auto-register at the proxy (e.g. https://172.28.0.2:3004/register) with mTLS.
- **Console verification** repeated: proj1/proj2 CLI apps (hello_cli, calc_cli) run correctly.
- **To repeat the full operation via proxy:** ensure code-analysis-server is registered in the proxy (e.g. proxy at 172.28.0.2:3004 reachable so server can auto-register on startup, or fix manual register_server UUID handling).

---

## When server is reachable again

1. **Editing (optional):**  
   `cst_load_file`(project_id=aea6ed9a..., file_path=hello_cli.py) → get `tree_id` → `cst_find_node` / `cst_modify_tree` (e.g. replace print line) → `cst_save_tree`.

2. **Delete projects:**  
   - `delete_project`(project_id=aea6ed9a-9fdd-4ef6-b1f7-4d719812f2e3, delete_from_disk=true)  
   - `delete_project`(project_id=19adc693-eb6c-448c-ba52-2723b36cf2bb, delete_from_disk=true)  

   This will clear DB and move `test_data/proj1` and `test_data/proj2` to trash.

---

## Summary

| Step                    | Status   | Note                                      |
|-------------------------|----------|-------------------------------------------|
| 1. Create two projects  | Done     | Via create_project                        |
| 2. Create 2 CLI apps × 2 projects | Done | Via cst_convert_and_save (4 files)        |
| 3. Verify in console    | Done     | All 6 runs OK                             |
| 4. Edit via server      | Blocked  | Proxy cannot connect to server            |
| 5. Delete via server    | Blocked  | Same; run delete_project when server is up |

Creating and editing project code via the server is a valid way to test; the blocker is connectivity between MCP Proxy and code-analysis-server, not the server commands themselves.
