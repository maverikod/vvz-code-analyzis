# Implementation plan: Unified CST node ID and batch read-only output handling

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**TZ:** [../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md](../TZ_UNIFIED_CST_NODE_ID_AND_BATCH_READ_ONLY.md)

---

## Role of execution model

**Role:** Senior Python developer and integrator.  
Implement exactly this plan and TZ with no scope creep.

---

## Canonical validation metrics

### Valid code metrics

- Must fully comply with project and user rules.
- Must not contain hardcode, placeholders, compatibility fallbacks unless explicitly requested.
- Must not contain incomplete code:
  - TODO/FIXME.
  - `NotImplemented` outside abstract methods.
  - `pass` outside exception bodies.
- Must not deviate from task scope.
- Abstract methods must not contain implementation logic beyond `NotImplemented`, docstring, and comments.

### Valid task metrics (for each step)

- Exact role is defined.
- Internal consistency.
- Completeness.
- Precision.
- Consistency with project rules.
- 100% handoff readiness.
- Mandatory blackstops.
- Mandatory re-check and fixes after coding.

### Valid plan metrics

- Steps are split into separate files under `../steps/`.
- **1 step = 1 code file = 1 step description file**.
- Step sequence respects dependencies.
- Each step is self-sufficient via links and context.
- Parallel execution chains are described in a separate file.

---

## Mandatory checks after each code step

1. Re-read step file and confirm all outputs are implemented exactly.
2. Run and fix:
   - `code_mapper -r code_analysis`
   - `black <touched_file>`
   - `flake8 <touched_file>`
   - `mypy <touched_file>`
3. Re-run command behavior checks for the step and fix regressions.
4. Confirm no violations of "valid code metrics".

---

## Step map (1 step = 1 code file)

| Step | Code file | Description |
|------|-----------|-------------|
| [Step 01](../steps/step_01_schema_nullable.md) | `code_analysis/core/database/base.py` | Add nullable `cst_node_id` columns for `classes/functions/methods` in schema/init path |
| [Step 02](../steps/step_02_backfill_script.md) | `scripts/backfill_entity_cst_node_id.py` | Implement one-off backfill script for existing rows |
| [Step 03](../steps/step_03_schema_not_null.md) | `code_analysis/core/database/schema_sync.py` | Enforce final `NOT NULL` state for `cst_node_id` |
| [Step 04](../steps/step_04_index_write_validation.md) | `code_analysis/core/database/files.py` | Populate and validate UUID4 `cst_node_id` on writes |
| [Step 05](../steps/step_05_hierarchy_response.md) | `code_analysis/commands/ast/hierarchy.py` | Return `file_path` + `cst_node_id` in hierarchy entities |
| [Step 06](../steps/step_06_list_entities_response.md) | `code_analysis/commands/ast/list_entities.py` | Return `file_path` + `cst_node_id` in list entities |
| [Step 07](../steps/step_07_entity_info_response.md) | `code_analysis/commands/ast/entity_info.py` | Return `file_path` + `cst_node_id` in entity info |
| [Step 08](../steps/step_08_dependencies_response.md) | `code_analysis/commands/ast/dependencies.py` | Return `file_path` + `cst_node_id` in dependencies |
| [Step 09](../steps/step_09_usages_response.md) | `code_analysis/commands/ast/usages.py` | Return `file_path` + `cst_node_id` in usages |
| [Step 10](../steps/step_10_entity_dependencies_response.md) | `code_analysis/commands/ast/entity_dependencies.py` | Return `file_path` + `cst_node_id` in entity deps/dependents |
| [Step 11](../steps/step_11_graph_response.md) | `code_analysis/commands/ast/graph.py` | Return `file_path` + `cst_node_id` in graph entity nodes |
| [Step 12](../steps/step_12_mutation_uuid4_modify_tree.md) | `code_analysis/commands/cst_modify_tree_command.py` | Enforce UUID4 node IDs as primary mutation target |
| [Step 13](../steps/step_13_mutation_uuid4_compose.md) | `code_analysis/commands/cst_compose_module_command.py` | Enforce UUID4 node IDs in compose mutation path |
| [Step 14](../steps/step_14_batch_read_only_command.md) | `code_analysis/commands/read_only_batch_command.py` | Batch command orchestration only (no storage internals) |
| [Step 15](../steps/step_15_batch_config.md) | `code_analysis/core/config.py` | Add config keys for batch threshold/output policy |
| [Step 16](../steps/step_16_batch_mcp_registration.md) | `code_analysis/commands/ast_mcp_commands.py` | Register/expose batch command in MCP layer |
| [Step 17](../steps/step_17_batch_whitelist_module.md) | `code_analysis/commands/read_only_batch_whitelist.py` | Hardcoded read-only whitelist with explicit validation helpers |
| [Step 18](../steps/step_18_batch_output_storage.md) | `code_analysis/commands/read_only_batch_output.py` | Oversize serialization/output file metadata (`size/offset/length`) |
| [Step 19](../steps/step_19_batch_command_tests.md) | `tests/test_read_only_batch_command.py` | Positive/negative tests for whitelist and oversize path |

---

## Dependencies

- 01 -> 02 -> 03 -> 04 is strict sequence (schema/backfill/final constraints/write validation).
- 05-11 depend on 04.
- 12-13 depend on 04 (UUID4 validation contract in place).
- 14 depends on 05-11 and 17 and 18.
- 15 depends on 14.
- 16 depends on 14 and 15.
- 19 depends on 14, 15, 16, 17, 18.

Parallelizable chains are defined in [PARALLEL_CHAINS.md](PARALLEL_CHAINS.md).

---

## Global blackstops

- No fallback compatibility behavior unless explicitly required.
- No line/range as primary identity for mutation targets.
- No mutating command allowed in batch read-only whitelist.
- No invalid/empty/non-UUID4 `cst_node_id` in DB writes or command responses.
- No partial implementation handoff.

---

## Final gate

- Execute full step checklist.
- Re-check all acceptance criteria from TZ.
- Confirm all touched files pass code_mapper, black, flake8, mypy.
- Confirm batch oversize path returns `output_file`, `file_size`, `size/offset/length` and no oversized inline payload.
