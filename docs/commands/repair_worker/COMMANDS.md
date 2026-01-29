# Repair Worker Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

All in `commands/repair_worker_mcp_commands.py`. Core: repair worker process management. Schema from `get_schema()`; metadata from `metadata()`.

---

## start_repair_worker — StartRepairWorkerMCPCommand

**Description:** Start the repair worker process.

**Behavior:** Launches the repair worker (e.g. subprocess or managed worker); returns status or PID.

---

## stop_repair_worker — StopRepairWorkerMCPCommand

**Description:** Stop the repair worker process.

**Behavior:** Stops the running repair worker gracefully or by signal; returns success/failure.

---

## repair_worker_status — RepairWorkerStatusMCPCommand

**Description:** Get current status of the repair worker (running, stopped, PID, last activity).

**Behavior:** Returns process status and optional log tail or health info.
