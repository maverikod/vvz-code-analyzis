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

### 1.5 Regression: manager timeout now at add_job stage (Step 05)

Independent MCP validation confirms a **stricter** regression: the manager process-control channel degrades already at **enqueue** time, not only at status/stop.

**Observed when regression occurs:**

1. **Enqueue:** `comprehensive_analysis(project_id="<id>", use_queue=true)`  
   - Response may include `job_id`, but the result contains failure:  
   - `Process control error for job 'manager' during add_job ... timed out waiting for response`
2. **Follow-up:** `queue_get_job_status(job_id)` fails with the same manager timeout.
3. **Follow-up:** `queue_stop_job(job_id)` fails with the same manager timeout.

**Key response fields (concise):**

| Operation        | Success | Key error message (excerpt) |
|------------------|--------|-----------------------------|
| add_job (enqueue)| false  | Process control error for job 'manager' during add_job ... timed out waiting for response |
| get_job_status   | false  | Process control error for job 'manager' during get_job_status ... timed out waiting for response |
| stop_job         | false  | Process control error for job 'manager' during stop_job ... timed out waiting for response |

**Payloads to reproduce:**

- Enqueue: `call_server(server_id="code-analysis-server", command="comprehensive_analysis", params={"project_id": "<project_id>"}, use_queue=True)`
- Status: `queue_get_job_status` with `params={"job_id": "<job_id from enqueue>"}`
- Stop: `queue_stop_job` with `params={"job_id": "<job_id from enqueue>"}`

This indicates the issue is **operation-agnostic** and points to a shared manager control bottleneck or deadlock in the adapter, not to a specific command handler.

---

## 2. Local impact analysis (code_analysis repository)

### 2.1 What is blocked operationally

- **Command queue unusable for long-running tasks** when manager timeout occurs at `add_job`: enqueue itself fails or returns with a failure, so no reliable `job_id` for tracking.
- Reliable monitoring of long-running queued jobs (`queue_get_job_status`) when the manager is under load.
- Reliable cancellation of queued jobs (`queue_stop_job`) in the same conditions.
- **Orchestration cannot reliably track or stop queued jobs** when any of add_job / get_job_status / stop_job hit the manager timeout.
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
  - `add_job` (enqueue request to manager),
  - `get_job_status` (status request to manager),
  - `stop_job` (stop request to manager).
- **Suspected causes:** Unbounded or long blocking wait on manager response, lock contention in the manager worker, or deadlock in the manager command channel when under load (e.g. during heavy `comprehensive_analysis` work). The regression from "stop_job-only" to "add_job + status + stop" suggests a shared control bottleneck.
- **Evidence:** Error text explicitly references job `'manager'` and “timed out waiting for response”, indicating the timeout occurs in the process-control layer talking to the manager, not in the application job itself.

### 3.2 Suggested adapter-side acceptance test

1. **Full control-path scenario (required):** Enqueue via a call that triggers `add_job` (e.g. `comprehensive_analysis(..., use_queue=true)`); then call `queue_get_job_status(job_id)`; then call `queue_stop_job(job_id)`. **Pass criteria:** No manager timeout on any of the three operations; each returns within a bounded time (e.g. &lt; 10 s) with either success or a deterministic error (e.g. job not found, already stopped). Never "Process control error for job 'manager' … timed out waiting for response".
2. **Stress variant:** Start a long-running queued job (60+ seconds); after 20–40 s, poll `queue_get_job_status` 3–5 times, then `queue_stop_job`. Same pass criteria.
3. **Optional:** Multiple concurrent long-running jobs to stress the manager process-control path.


---

## 4. Exit criteria (Step 04)

- [x] Reproducible packet with command payloads, exact error responses, and expected vs actual behavior is documented.
- [x] Local impact analysis (blocked operations, local resilience/ownership) is documented.
- [x] External handoff section with suspected adapter area and suggested acceptance test is included.
- [x] Queue track can be marked completed under the EXTERNAL_ADAPTER branch without editing foreign (adapter) package code.

This escalation packet is sufficient for external developers to reproduce the issue without extra clarifications.

---

## 5. Local temporary guardrail recommendation (Step 05)

**Failure signature:** Response (from enqueue, `queue_get_job_status`, or `queue_stop_job`) contains substring `Process control error for job 'manager'` and `timed out waiting for response`.

**Recommendation:** In this repository, when invoking adapter queue commands or handling their responses, detect this failure signature and **fail fast** with a deterministic, operator-friendly message:

- **Error code / identifier:** `EXTERNAL_ADAPTER_QUEUE_MANAGER_TIMEOUT`
- **Message (example):** `Queue manager timeout (adapter): process control for job 'manager' timed out. See escalation packet STEP_04_EXTERNAL_ESCALATION_PACKET.md.`

This gives operators a clear, searchable signal and avoids confusion with other timeout or queue errors. Implementation can live in the MCP command layer or in a thin wrapper that parses adapter responses before returning to the client.
