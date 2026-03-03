"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Step 00 - Queue Ownership Gate: Decision Artifact

## Conclusion

**Ownership: `EXTERNAL_ADAPTER`**

Queue timeout (`Process control error for job 'manager' ... timed out waiting for response`) is **not** caused by code in this repository. The failing code path belongs to **mcp-proxy-adapter**. This repo completes the queue track via **Step 04** (escalation packet + local resilience if applicable). **Step 03 is skipped.**

---

## Evidence

### 1. Adapter ownership of `queue_*` commands

- **Source:** `scripts/command_inventory.py` (lines 67–74) lists standard adapter commands:

  - `queue_add_job`, `queue_start_job`, `queue_stop_job`, `queue_delete_job`
  - `queue_get_job_status`, `queue_get_job_logs`, `queue_list_jobs`, `queue_health`

- These are **excluded** from project-specific command discovery (inventory treats them as built-in adapter commands). The code-analysis-server **does not implement** any of the `queue_*` MCP commands; they are provided by the adapter.

### 2. No queue command implementation in this repo

- **Search:** `queue_get_job_status`, `queue_stop_job`, `queue_add_job` in `code_analysis/`:
  - Only **references in docs/help** (e.g. `comprehensive_analysis_mcp.py`, `update_indexes_metadata.py`, `main.py`) telling users to use `queue_get_job_status` / `queue_get_job_logs`.
  - **No command class** in `code_analysis/commands/` that implements `queue_get_job_status` or `queue_stop_job`.

- Therefore the MCP flow is: **Client → MCP Proxy (adapter) → adapter’s queue manager**. The code-analysis-server is only the **target** of queued commands (e.g. `comprehensive_analysis`); it does not host the queue or the status/stop handlers.

### 3. Error message points to adapter’s “manager” job

- Observed error: `Process control error for job 'manager' ... Command timed out waiting for response`.
- The literal **job 'manager'** indicates the adapter’s internal process-control channel (manager process), not a job ID from this server. Timeout occurs in the **adapter’s** communication with that manager.

### 4. Local RPC client is for database driver only

- **File:** `code_analysis/core/database_client/rpc_client.py`.
- It uses methods `get_job_status` and `stop_job` for **database driver** request-queue control (DB worker process), with shorter timeouts and retries to avoid blocking.
- That path is **unrelated** to MCP `queue_get_job_status` / `queue_stop_job`. The adapter does **not** forward those MCP commands to the code-analysis-server; they are handled entirely inside the adapter.

---

## Decision

| Criterion                         | Result                |
|----------------------------------|-----------------------|
| Failing code path in this repo?  | No                    |
| Queue commands implemented here? | No (adapter-only)     |
| Ownership                        | **EXTERNAL_ADAPTER**  |

**Next actions:**

- **Step 03** (queue timeout local fix): **SKIPPED** — no local queue command file to change.
- **Step 04** (escalation packet): **EXECUTE** — produce adapter bug report and document local impact/resilience.
