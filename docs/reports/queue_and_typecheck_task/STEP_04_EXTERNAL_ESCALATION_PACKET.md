# Step 04 – Queue External Adapter Escalation Packet (EXTERNAL_ADAPTER branch)

**Author:** Vasiliy Zdanovskiy  
**email:** <vasilyvz@gmail.com>

**Step:** `steps/step_04_queue_external_escalation_packet.md`  
**Chain:** B-QUEUE, Parallel group P2  
**Ownership decision:** EXTERNAL_ADAPTER  
**Date:** 2025-03-03  

This document is a **ready-to-send bug report** for mcp-proxy-adapter maintainers. Root cause of queue manager timeout has been attributed to the adapter; this repository does not modify adapter code and completes the queue track via this escalation package.

---

## 1. Reproducible packet

### 1.1 Prerequisites

- MCP Proxy connected to code-analysis-server.
- A registered project with known `project_id` (e.g. `vast_srv` in test_data).
- No schema or contract changes required; standard adapter commands are used.

### 1.2 Command payloads (exact sequence)

#### Step A – Enqueue long-running job

- Command: `comprehensive_analysis`
- Params (example): `{"project_id": "<vast_srv_project_id>"}` (or as required by server schema)
- Expected: Response includes `job_id` (e.g. `comprehensive_analysis_41df0284`).

#### Step B – Wait

- Action: Wait 20–40 seconds so the job is running and manager is under load.

#### Step C – Poll job status (repeat at least 3 times)

- Command: `queue_get_job_status`
- Params: `{"job_id": "comprehensive_analysis_41df0284"}` (use actual `job_id` from Step A).

#### Step D – Stop job

- Command: `queue_stop_job`
- Params: `{"job_id": "comprehensive_analysis_41df0284"}`.

### 1.3 Exact error responses (observed)

- **`queue_get_job_status`:**  
  `Failed to get job status ... Process control error for job 'manager' during get_job_status ... timed out waiting for response`

- **`queue_stop_job`:**  
  `Failed to stop job ... Process control error for job 'manager' during stop_job ... timed out waiting for response`

*(Exact wording may include minor variations; the key substring is: `Process control error for job 'manager'` and `timed out waiting for response`.)*

Timestamps: observed during MCP-based testing when status/stop were invoked 20–40 seconds after starting a queued `comprehensive_analysis` job. Reproducibility is intermittent under load.

### 1.4 Expected vs actual behavior

| Aspect | Expected | Actual |
| ------ | -------- | ------ |
| `queue_get_job_status` | Returns job status (e.g. running, completed, failed) or a clear job-level error within a bounded time. | Times out with process-control error for job `manager`; no status returned. |
| `queue_stop_job` | Stops the job or returns a deterministic error (e.g. job not found, already stopped) within a bounded time. | Times out with process-control error for job `manager`; stop outcome unknown. |
| Manager process control | Status/stop requests to the manager complete or fail quickly with a defined error. | Waits until timeout; no success, no bounded failure. |

---

## 2. Local impact analysis (code_analysis repository)

### 2.1 What is blocked operationally

- Reliable monitoring of long-running queued jobs (`queue_get_job_status`) when the manager is under load.
- Reliable cancellation of queued jobs (`queue_stop_job`) in the same conditions.
- Downstream workflows that depend on status/stop (e.g. UI progress, cancellation) become unreliable when timeouts occur.

### 2.2 Local resilience in this repository

- **No adapter code edits:** This repo does not modify mcp-proxy-adapter; queue semantics remain adapter-owned.
- **Integration interface:** code_analysis uses only adapter queue commands (`queue_add_job`, `queue_get_job_status`, `queue_stop_job`, etc.) as the integration boundary.
- **Optional local mitigations (if added elsewhere):** Any retries, backoff, or clearer error mapping in this repo would be limited to the caller side (e.g. bounded retries, timeouts, and surfacing the adapter error unchanged). Such changes do not fix the underlying manager process-control timeout in the adapter.
- **Queue ownership evidence:** `queue_*` commands are standard adapter commands; see `scripts/command_inventory.py` → `get_standard_adapter_commands()` (e.g. `queue_get_job_status`, `queue_stop_job`, `queue_add_job`, `queue_list_jobs`, etc.). They are not implemented in code_analysis.

---

## 3. External handoff (for adapter maintainers)

### 3.1 Minimal suspected adapter area

- **Component:** Queue manager process-control path.
- **Likely locations:** Handlers or wrappers that perform process-control communication with the job `manager` for:
  - `get_job_status` (status request to manager),
  - `stop_job` (stop request to manager).
- **Suspected causes:** Unbounded or long blocking wait on manager response, lock contention in the manager worker, or deadlock in the manager command channel when under load (e.g. during heavy `comprehensive_analysis` work).
- **Evidence:** Error text explicitly references job `'manager'` and “timed out waiting for response”, indicating the timeout occurs in the process-control layer talking to the manager, not in the application job itself.

### 3.2 Suggested adapter-side acceptance test

1. Start a long-running queued job (e.g. a job that runs 60+ seconds).
2. After 20–40 seconds, in a loop (e.g. 3–5 times), call `queue_get_job_status` with that job’s ID.
3. Call `queue_stop_job` with the same job ID.
4. **Pass criteria:** Every `queue_get_job_status` and `queue_stop_job` returns within a bounded time (e.g. &lt; 10 s) with either success or a deterministic error (e.g. job not found, already stopped), and never with “Process control error for job 'manager' … timed out waiting for response”.
5. **Optional:** Run the same test with multiple concurrent long-running jobs to stress the manager process-control path.

---

## 4. Exit criteria (Step 04)

- [x] Reproducible packet with command payloads, exact error responses, and expected vs actual behavior is documented.
- [x] Local impact analysis (blocked operations, local resilience/ownership) is documented.
- [x] External handoff section with suspected adapter area and suggested acceptance test is included.
- [x] Queue track can be marked completed under the EXTERNAL_ADAPTER branch without editing foreign (adapter) package code.

This escalation packet is sufficient for external developers to reproduce the issue without extra clarifications.
