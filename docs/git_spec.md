# TZ-CA-GIT-COMMANDS-001 — project-scoped git command block

```
Project:    code-analyzis (CA), code-analysis-server
Status:     DRAFT for review
Author:     Vasiliy Zdanovskiy <vasilyvz@gmail.com>
Scope:      A block of MCP commands that operate git on a *registered project's*
            working tree (resolved from project_id, under a watch directory).
```

## 1. Purpose & context

The server already has:

- `core/git_integration.py` — subprocess `git` helpers for a project tree
  (`is_git_available`, `is_git_repository`, `create_git_commit`,
  `create_git_commit_paths`) plus the `code_analysis.git_commit_on_write`
  auto-commit hook used by mutating file commands.
- `session_git_*` commands (`status/log/show/diff/revert`) — but those are
  **edit-session scoped** (operate on the temp edit-session repo by `session_id`),
  not on the project repository.

What is missing is a **project-scoped** git command block: status / log / diff /
branch / commit / pull / push / … against the registered project's working tree
(`projects.root_path` resolved to an absolute path under a watch directory). This
is exactly the operation performed manually when the server's own
`code-analyzis` checkout was updated.

Decisions taken at design review:

- **Scope:** full set — read-only + local mutating + remote.
- **Auth:** SSH key bytes live in `secrets/`; the git *account* (key path,
  identity, policy) lives in a dedicated `code_analysis.git` config subsection.
- **Safety:** destructive/remote operations gated by explicit flags + `dry_run`;
  pushes to protected branches blocked by config.
- **Engine:** subprocess `git` (consistent with `git_integration.py`). The
  daemon runs as the unprivileged server user (`casuser`) both on the legacy
  host deployment and inside the all-in-one container (its uid/gid matched
  to the host `casuser` via `CASMGR_UID`/`CASMGR_GID`, dropped via `gosu`
  from the container's root PID 1), so writes stay `casuser:casgrp` with no
  post-hoc `chown` in either case. `CASMGR_ALLOW_ROOT` (see
  `core/project_git/execution_context.py`) remains as a safety guard but is
  not exercised in normal operation, since the daemon is never root.

## 2. Configuration subsection: `code_analysis.git`

Holds **paths and identity only — never secret bytes**. The private key lives in
the secrets directory (`/var/casmgr/secrets/git/…`), owned `casuser:casgrp`,
mode `0600` (ssh refuses group/world-readable keys).

```jsonc
"code_analysis": {
  "git": {
    "enabled": true,
    "ssh_key_path": "/var/casmgr/secrets/git/id_ed25519",
    "known_hosts_path": "/var/casmgr/secrets/git/known_hosts",
    "strict_host_key_checking": true,         // -o StrictHostKeyChecking=yes
    "user_name": "casmgr-bot",                // commit identity (-c user.name=)
    "user_email": "casmgr@local",             // commit identity (-c user.email=)
    "protected_branches": ["main", "master"], // push blocked unless override
    "allow_push": true,
    "allow_force_push": false,                // force-push needs this AND force=true
    "remote_timeout_seconds": 120
  }
}
```

Validation (config_validator): `ssh_key_path`/`known_hosts_path` non-empty when
any remote op is used; `remote_timeout_seconds >= 1`; `protected_branches` a list
of non-empty strings; booleans typed. Missing/disabled `git` section ⇒ remote
commands fail fast with `GIT_REMOTE_NOT_CONFIGURED`; local/read commands still work.

## 3. Authentication & access (recommended mechanism)

Every **remote** command (`fetch`/`pull`/`push`) injects a per-process SSH wrapper;
no global ssh/git config is mutated and no ssh-agent is required:

```
GIT_SSH_COMMAND = ssh -i <ssh_key_path>
                      -o IdentitiesOnly=yes
                      -o UserKnownHostsFile=<known_hosts_path>
                      -o StrictHostKeyChecking={yes|accept-new}
                      -o ConnectTimeout=<min(remote_timeout, 30)>
```

Commit identity is passed inline per invocation: `git -c user.name=<…>
-c user.email=<…> commit …` — no dependency on `~/.git config` (the server user
has `HOME=/nonexistent`).

Rationale:
- Secret bytes never leave `secrets/` (`0600 casuser`); config stores only a path.
- `IdentitiesOnly=yes` → exactly the configured key, no agent/other-key fallback.
- `StrictHostKeyChecking=yes` + pinned `known_hosts` → no MITM, no interactive
  prompt (CI/headless safe). Operators pre-seed `known_hosts` (e.g. `ssh-keyscan
  github.com`).
- The server runs as `casuser` on both deployment models — the legacy host
  install and the all-in-one container (uid/gid injected via
  `CASMGR_UID`/`CASMGR_GID`, dropped from root via `gosu`); subprocess git
  inherits it, so created/updated files and `.git` objects are always
  `casuser:casgrp` with no post-hoc `chown` — see §5 for the one legitimate
  runtime `os.chown` exception in this codebase.

HTTPS+token is an explicit non-goal for v1 (kept out to avoid token storage/rotation);
revisit only if an SSH key per host is impractical.

## 4. Command catalog (prefix `git_`)

All commands: `project_id` required; resolve the absolute repo root via the
project registry (`resolve_project_root_absolute_str` / `get_project().root_path`);
verify `is_git_repository(root)` else `GIT_NOT_A_REPO`; run `git` with `cwd=root`;
return structured data; paths in params/results are **project-relative POSIX**.

### 4.1 Read-only (`use_queue=false`)

| Command | Params | Returns |
|---|---|---|
| `git_status` | `project_id` | `branch`, `upstream`, `ahead`, `behind`, `staged[]`, `unstaged[]`, `untracked[]`, `clean` |
| `git_log` | `project_id`, `limit=20`, `block_position=1`, `path?`, `author?`, `since?` | paginated `items[]` = {`hash`, `author`, `date`, `subject`} |
| `git_diff` | `project_id`, `mode=working\|staged\|range`, `ref_a?`, `ref_b?`, `path?`, `name_only=false` | `files[]` (+ stats) or unified `diff` text |
| `git_branch` | `project_id` | `current`, `branches[]` = {`name`, `current`, `upstream`, `ahead`, `behind`} |
| `git_show` | `project_id`, `ref` | commit metadata + diff/stat |
| `git_remote` | `project_id` | `remotes[]` = {`name`, `fetch_url`, `push_url`} |

### 4.2 Local mutating (`use_queue=false`, fast)

| Command | Params | Notes |
|---|---|---|
| `git_add` | `project_id`, `paths[]?`, `all=false` | stage paths or `-A` |
| `git_commit` | `project_id`, `message`, `paths[]?`, `allow_empty=false` | identity from config; returns `hash`; reuses `create_git_commit*` |
| `git_switch` | `project_id`, `branch`, `create=false`, `from_ref?` | switch/create branch |
| `git_restore` | `project_id`, `paths[]`, `source?`, `staged=false` | restore working/staged files |
| `git_branch_create` | `project_id`, `name`, `from_ref?` | |
| `git_branch_delete` | `project_id`, `name`, `force=false` | |
| `git_stash` | `project_id`, `action=save\|pop\|list\|drop`, `message?`, `index?` | |
| `git_reset` | `project_id`, `mode=soft\|mixed\|hard`, `ref=HEAD`, `dry_run=false` | `hard` requires explicit `mode=hard` **and** is `dry_run` by default unless `confirm=true` |

### 4.3 Remote (`use_queue=true`, long-running, needs `code_analysis.git`)

| Command | Params | Notes |
|---|---|---|
| `git_fetch` | `project_id`, `remote=origin`, `prune=false` | |
| `git_pull` | `project_id`, `remote=origin`, `branch?`, `ff_only=true`, `rebase=false` | `ff_only` default true (safe); conflicts ⇒ `GIT_CONFLICT`, no partial state |
| `git_push` | `project_id`, `remote=origin`, `branch=<current>`, `set_upstream=false`, `force=false`, `dry_run=false` | protected-branch + force policy (see §5) |

`git_clone` is intentionally **out of v1**: project materialization is owned by
`create_project` / watch-dir discovery; cloning is a separate concern.

## 5. Safety / guards

- **Not a repo / git missing** → `GIT_NOT_A_REPO` / `GIT_NOT_AVAILABLE` (clear, non-fatal).
- **Path confinement**: every path param is normalized and must resolve **inside**
  the project root; reject traversal (`GIT_PATH_OUTSIDE_PROJECT`).
- **Destructive ops** (`git_reset mode=hard`, future `clean`): require the explicit
  mode/flag; default to `dry_run` (report what would change) unless `confirm=true`.
- **Force push**: `force=true` allowed only when config `allow_force_push=true`;
  otherwise `GIT_FORCE_PUSH_DISABLED`.
- **Protected branches**: `git_push` to a branch in `protected_branches` is rejected
  with `GIT_PROTECTED_BRANCH` unless the request carries an explicit override
  (`allow_protected=true`) **and** policy permits it.
- **`dry_run`** on `git_push` → `git push --dry-run`; on `git_pull` → fetch + report
  without merge; on `git_reset` → report target without moving HEAD/worktree.
- **Timeouts**: remote ops bounded by `remote_timeout_seconds`; on timeout
  `GIT_TIMEOUT`, no retry inside the command.
- **Ownership**: these commands rely on the unprivileged server user
  (`casuser`) on both deployment models, so writes are always
  `casuser:casgrp` with no `chown`. In the all-in-one container, the
  daemon's uid/gid are matched to the host `casuser` via `CASMGR_UID`/
  `CASMGR_GID` (set from the host's real numeric ids by `debian/postinst`)
  and dropped via `gosu` from the container's root PID 1 before the daemon
  starts; `CASMGR_ALLOW_ROOT` (see `check_unprivileged_execution_context`
  in `core/project_git/execution_context.py`) remains as a safety guard but
  is not used in normal operation, since the daemon is never root. The
  single legitimate runtime `os.chown` anywhere in this codebase is
  `code_analysis/core/tree_file_write.py:match_file_owner` (~line 40), which
  preserves the *source file's* existing owner when writing a `.cst`/`.tree`
  sidecar next to it (falling back to the parent directory's owner when the
  source does not yet exist); it does not claim ownership for the daemon
  itself and its behavior is unaffected by `CASMGR_ALLOW_ROOT`.

## 6. Error codes (stable)

`PROJECT_NOT_FOUND`, `GIT_NOT_A_REPO`, `GIT_NOT_AVAILABLE`,
`GIT_REMOTE_NOT_CONFIGURED`, `GIT_AUTH_FAILED`, `GIT_PROTECTED_BRANCH`,
`GIT_FORCE_PUSH_DISABLED`, `GIT_PUSH_REJECTED`, `GIT_CONFLICT`,
`GIT_PATH_OUTSIDE_PROJECT`, `GIT_DESTRUCTIVE_REQUIRES_CONFIRM`, `GIT_TIMEOUT`,
`GIT_COMMAND_FAILED` (carries `stderr`, `exit_code`).

## 7. Implementation notes

- New module `core/git_project_ops.py`: thin subprocess wrappers returning
  `(ok, data, error)`; builds `GIT_SSH_COMMAND` from `code_analysis.git`; reuses
  `is_git_available`/`is_git_repository`/`create_git_commit*` from `git_integration.py`.
- One `BaseMCPCommand` subclass per command under
  `commands/git_project_mcp_commands/`, registered like the other 128 commands.
  Read/local ⇒ `use_queue=False`; remote ⇒ `use_queue=True` (`job_id` + poll).
- Project root resolution reuses `project_root_path.resolve_project_root_absolute_str`
  (never CWD); refuse when it resolves empty (consistent with the `add_file` guard).
- This block does **not** touch the command→universal-driver→specific-driver→DBMS
  chain; it operates only on the filesystem working tree via subprocess git.

## 8. Acceptance (high level)

- A-1: `git_status`/`git_log`/`git_diff`/`git_branch`/`git_show`/`git_remote` return
  structured data for a registered project repo; `GIT_NOT_A_REPO` for non-repos.
- A-2: `git_add`+`git_commit` create a commit authored by the configured identity;
  files remain `casuser:casgrp`.
- A-3: `git_pull --ff-only` fast-forwards using the configured key; conflict ⇒
  `GIT_CONFLICT` with clean tree.
- A-4: `git_push` to `main` blocked by `GIT_PROTECTED_BRANCH`; force-push blocked
  unless `allow_force_push=true` + `force=true`; `dry_run=true` performs no remote write.
- A-5: remote commands with missing `code_analysis.git` ⇒ `GIT_REMOTE_NOT_CONFIGURED`;
  local/read commands still function.
- A-6: on both the legacy host deployment and the all-in-one container
  deployment, all created/updated files and `.git` objects are owned
  `casuser:casgrp` (the container daemon's uid/gid are matched to the host
  `casuser` via `CASMGR_UID`/`CASMGR_GID`); there is no root-owned artifact
  trade-off in this model.
```
