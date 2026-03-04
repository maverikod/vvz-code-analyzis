# Step 05 Completion Report: Queue Timeout Regression at add_job (EXTERNAL_ADAPTER)

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Step:** `steps/step_05_queue_timeout_regression_add_job.md`  
**Chain:** B-QUEUE, Parallel group P3  
**Date:** 2025-03-03  

---

## 1. STATUS: SUCCESS

Step 05 is complete. Escalation packet updated; regression from stop_job-only to add_job + status + stop is documented; local guardrail recommendation added.

---

## 2. Confirmed reproduction table

**When regression occurs** (from step description and escalation packet):

| Operation        | Success | Key error message |
|------------------|--------|--------------------|
| add_job (enqueue)| false  | Process control error for job 'manager' during add_job ... timed out waiting for response |
| get_job_status   | false  | Process control error for job 'manager' during get_job_status ... timed out waiting for response |
| stop_job         | false  | Process control error for job 'manager' during stop_job ... timed out waiting for response |

**MCP reproduction run (2025-03-03):** One enqueue was executed via `call_server(server_id="code-analysis-server", command="comprehensive_analysis", params={"project_id": "c86dded6-6f93-4fb0-be54-b6d7b739eeb9"}, use_queue=True)`. Result: **add_job succeeded** (job_id `comprehensive_analysis_19776dd4`, status pending). Regression is intermittent; when it occurs, the three operations above show the same manager timeout signature.

---

## 3. Updated external escalation content (excerpts)

- **Section 1.5** added: "Regression: manager timeout now at add_job stage" with:
  - Observed behavior (enqueue may return job_id but result includes add_job timeout; get_job_status and stop_job fail with same timeout).
  - Table: operation / success / key error message for add_job, get_job_status, stop_job.
  - Payloads to reproduce (call_server comprehensive_analysis use_queue=True; queue_get_job_status; queue_stop_job).
- **Section 2.1** extended: command queue unusable for long-running tasks when timeout at add_job; orchestration cannot reliably track or stop queued jobs.
- **Section 3.1** extended: add_job added to suspected adapter operations; regression from stop_job-only to add_job + status + stop suggests shared control bottleneck.
- **Section 3.2** updated: acceptance test now requires one scenario covering **add_job → get_job_status → stop_job** with no manager timeouts; stress variant and optional concurrency retained.
- **Section 5** added: local temporary guardrail recommendation (failure signature, error code `EXTERNAL_ADAPTER_QUEUE_MANAGER_TIMEOUT`, fail-fast message).

---

## 4. Root-cause ownership conclusion

**EXTERNAL_ADAPTER.** Rationale: timeout is operation-agnostic (add_job, get_job_status, stop_job); error text references job `'manager'` and "timed out waiting for response"; queue_* commands are implemented in mcp-proxy-adapter, not in this repository; local code does not implement adapter queue command internals. Therefore root-cause implementation sits in external mcp-proxy-adapter.

---

## 5. Local guardrail recommendation (text)

- **Failure signature:** Response contains substring `Process control error for job 'manager'` and `timed out waiting for response`.
- **Action:** Detect this signature and fail fast with deterministic message.
- **Error code / identifier:** `EXTERNAL_ADAPTER_QUEUE_MANAGER_TIMEOUT`
- **Message (example):** `Queue manager timeout (adapter): process control for job 'manager' timed out. See escalation packet STEP_04_EXTERNAL_ESCALATION_PACKET.md.`
- **Place of implementation:** MCP command layer or thin wrapper that parses adapter responses before returning to the client.

---

## 6. Commit

After saving the doc updates, run (from repo root):

```bash
git add docs/reports/queue_and_typecheck_task/STEP_04_EXTERNAL_ESCALATION_PACKET.md docs/reports/queue_and_typecheck_task/STEP_05_COMPLETION_REPORT.md
git commit -m "Step 05: queue timeout regression at add_job - escalation packet and completion report"
```

**Commit:** `c94dd28` — Step 05: queue timeout regression at add_job - escalation packet and completion report
