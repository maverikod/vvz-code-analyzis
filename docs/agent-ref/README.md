# Claude project prompt template

This archive provides a thin-core, lazy-loaded multi-agent prompt architecture
for Claude. `CLAUDE.md` imports the mandatory common laws and orchestrator role;
children read their own role and triggered operation packs before acting.

## Required substitutions

- `code_analysis`, `{{PROJECT_ID}}`, `{{LOCAL_REPO}}`
- `code-analysis-server-vvz`, `ai-editor-server-vvz`, `mcp-terminal-vvz`,
  `planmgr`
- `root@192.168.254.26`, `./build.sh`, `scripts/verify_client_all_commands_live.py --host 192.168.254.26 --port 15010 (mint disposable mTLS cert per script docstring)`
- `pyproject.toml (root; scripts/sync_code_analysis_client_version.py syncs the client)`; add every lockstep version file required by the project
- `{{PROJECT_STANDARDS_DIR}}` only when the project supplies those standards;
  otherwise remove the manual entry and all role references to it

## Architecture

- `roles/common.yaml` and `roles/laws.yaml`: universal constraints
- `roles/<role>.yaml`: one role's authority and escalation boundary
- `modes.yaml`: lazy operating-mode triggers
- `servers/*.yaml`: thin registered-server maps
- `ops/*.yaml`: command procedures loaded only on matching triggers

The root orchestrator is the only user-facing agent. Child reports are untrusted
until independently checked against artifacts, tests, live behavior, and the
authoritative server state. Parents remain active until every descendant is
terminal.

## Editor contract

Do not carry historical workarounds forward as facts. Verify current live help,
health, version, and behavior. Maintain regression coverage for edit outcome
correlation, YAML root-key insertion, Python trailing header comments, statements
inside `try/except`, sibling-import validation, and native INI/TOML structured
editing.

A long operation may validly enter a queue. Configure the adapter client for
synchronous poll-and-unwrap or asynchronous/message handling. Queue handoff is
not itself a defect; terminal payload or exception determines the outcome.

## Branch transfer

`local` and `cas` are working branches; `main` is transfer-only. Never merge
`local` directly with `cas`. Build, deploy, and run live acceptance from the
active working branch. Merge it into local `main` only after production success,
report the exact commit, and wait for the user to push. After confirmation, the
opposite site pulls `main` and merges it into its own branch.

## Delivery

Keep exactly one real-server acceptance pipeline. The full chain is reproduce,
prove cause, fix, add focused coverage, run project checks, align versions, build,
deploy, run the live pipeline, verify registration and changed behavior through
MCP Proxy, and record a verified Plan Manager fix before closing a bug.

## Validation

Parse every YAML file, verify referenced package files exist, and limit remaining
`{{...}}` tokens to the substitutions listed above. Confirm live server IDs and
command schemas before first use.
