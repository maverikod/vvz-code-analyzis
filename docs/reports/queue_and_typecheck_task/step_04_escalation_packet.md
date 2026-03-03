"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Step 04 - Adapter Escalation Packet: Queue Manager Timeout

Ready-to-send bug report for **mcp-proxy-adapter** maintainers. Root cause of queue timeout is in the adapter; this repository does not implement `queue_*` commands.

---

## 1. Summary

**Issue:** `queue_get_job_status` and `queue_stop_job` intermittently fail with process-control timeout when a long-running job (e.g. `comprehensive_analysis`) is queued. Error refers to job `'manager'` and “timed out waiting for response”.

**Expected:** Status and stop operations complete within a bounded time (e.g. a few seconds) or return a deterministic error.

**Actual:** Operations time out; client receives “Process control error for job 'manager' … Command timed out waiting for response”.

---

## 2. Reproducible scenario

### 2.1 Commands and payloads

1. **Start a long-running job via queue**
   - Command: `comprehensive_analysis`
   - Params: `{"project_id": "<vast_srv_project_id>"}` (or equivalent UUID for a project with many files).
   - Result: job is accepted; `job_id` returned (e.g. `comprehensive_analysis_41df0284`).

2. **Wait**
   - 20–40 seconds (so the job is running and the manager is under load).

3. **Poll job status (at least 3 times)**
   - Command: `queue_get_job_status`
   - Params: `{"job_id": "<returned_job_id>"}` (e.g. `{"job_id": "comprehensive_analysis_41df0284"}`).
   - Observation: One or more calls fail with the timeout error below.

4. **Stop the job**
   - Command: `queue_stop_job`
   - Params: `{"job_id": "<returned_job_id>"}`.
   - Observation: Often fails with the same timeout error.

### 2.2 Exact error responses (excerpts)

- **queue_stop_job:**  
  `Failed to stop job ... Process control error for job 'manager' during stop_job ... timed out waiting for response`

- **queue_get_job_status:**  
  `Failed to get job status ... Process control error for job 'manager' during get_job_status ... timed out waiting for response`

(Exact wording may vary slightly; timestamps omitted here; can be captured in a full run.)

### 2.3 Environment

- Client: MCP client (e.g. Cursor) calling through MCP Proxy (adapter).
- Backend server: code-analysis-server (this repo); long-running command is `comprehensive_analysis`.
- Queue and process-control: fully owned by the adapter (queue manager / “manager” job).

---

## 3. Expected vs actual behavior

| Action                 | Expected                                      | Actual                                                                 |
|------------------------|-----------------------------------------------|------------------------------------------------------------------------|
| `queue_get_job_status` | Returns status (e.g. running/done) or clear error within a few seconds | Timeout; “Process control error for job 'manager' … timed out”         |
| `queue_stop_job`       | Job is stopped or clear error returned        | Same timeout error; stop may not be applied from client perspective   |

---

## 4. Local impact (code-analysis repo)

- **Blocked operations:** Users cannot reliably poll status or stop long-running queued jobs when the adapter’s process-control channel times out.
- **Local resilience:** This repository does not implement `queue_*`; it only documents their use. No local code change can fix the adapter’s manager timeout. Optional future work: document retry/backoff and timeouts for clients calling `queue_get_job_status` / `queue_stop_job` (client-side resilience only).

---

## 5. Suspected adapter area and suggested test

- **Suspected area:** Process-control path between the adapter and the “manager” job (channel used for `get_job_status` and `stop_job`). Possible causes: unbounded wait, lock contention in the manager, or blocking I/O without a short timeout.
- **Suggested acceptance test (adapter-side):**
  1. Enqueue a long-running job (e.g. one that runs 60+ seconds).
  2. Every 5–10 seconds, call `queue_get_job_status` for that job (e.g. 5–10 times).
  3. Then call `queue_stop_job` for that job.
  4. **Pass criteria:** All status and stop calls complete within a configured bound (e.g. 5–10 s) and return either success or a deterministic error (no “timed out waiting for response” for the manager job).

---

## 6. References

- Main task: `docs/reports/queue_and_typecheck_task/QUEUE_AND_TYPECHECK_ATOMIC_TASK.md`
- Ownership evidence: `docs/reports/queue_and_typecheck_task/step_00_ownership_decision.md`
- Step 04 spec: `docs/reports/queue_and_typecheck_task/steps/step_04_queue_external_escalation_packet.md`
