<!--
Tactical task — parent global step: fix_vast_srv_server_only_phase1
-->

# Tactical Task: vast_srv server-only Phase 1 — first fix batch

## Purpose

Execute the first bounded fix batch on `vast_srv` using only `code-analysis-server` (MCP), prioritizing explicit errors over unfinished code and duplicates, after the repaired analysis workflow is confirmed.

## Parent links

- `docs/tech_spec/tech_spec.md`
- `docs/tech_spec/steps/fix_vast_srv_server_only_phase1.md`

## Scope

**Included:** MCP-only reads/writes on `vast_srv`; `comprehensive_analysis` / `lint_code` / `type_check_code` / CST commands for fixes; reporting fixed vs remaining backlog.

**Excluded:** Direct repo tools on `test_data/vast_srv`; `coder_auto` / `tester_auto` touching `vast_srv`; unbounded refactors.

## Boundaries

- All guarded `vast_srv` paths: **tester_ca** only.
- Server defects: stop batch, route repair to **coder_auto** (this repo, not `vast_srv`), then resume MCP checkpoint.

## Dependencies

none (enters from revalidated C2 / summary-counting repair).

## Parallelization note

Serial: backlog pull → fixes → lint verify.

## Expected outcome

At least one concrete backlog item fixed with server commands; remaining backlog and blockers documented; workflow integrity stated.

## Correction items

none

## Questions/escalation rule

If CST replace clobbers parent nodes or compose validation blocks legitimate edits, escalate server-side fix to global orchestrator / **coder_auto**.

---

## Execution record (tester_ca evidence)

- **Entry:** `health` OK; `comprehensive_analysis_98ea9ab6` completed, `success: true`, summary `files_total` 598, trust keys consistent with skip-all incremental pass; no `COMPREHENSIVE_ANALYSIS_ERROR`.
- **Batch scope:** (1) `ai_admin/auth/git_auth_manager.py` — explicit flake8 E128; (2) `add_fallback_logic.py` — explicit F821 / f-string bug — **not completed** (tooling).
- **Fixed:** `git_auth_manager.py` — `format_code` (Black) cleared E128; `lint_code` 0 errors; `type_check_code` still 2 pre-existing mypy issues.
- **Blocked:** `add_fallback_logic.py` — unsafe `cst_modify_tree` replace on `Param`/`Name`; `query_cst` partial replace damaged structure (restored via `restore_backup_file`); `compose_cst_module` failed project validation.
- **Remaining backlog:** `add_fallback_logic.py` lint/mypy still failing; 139 long files in comprehensive snapshot; sample mypy on `git_auth_manager.py`.

## File inventory (vast_srv, via server)

| action | path (project-relative) |
|--------|-------------------------|
| modify | `ai_admin/auth/git_auth_manager.py` |
| restore | `add_fallback_logic.py` (backup after failed edit) |

## Checkpoint

**Next batch:** Unblock `add_fallback_logic.py` via **server CST repair** (`coder_auto`) or a **single safe `query_cst` full-function replace** with preview; then continue explicit-error queue. **Workflow:** MCP-only for `vast_srv` preserved for completed work.

---

## Continuation batch — `add_fallback_logic.py` explicit errors (post-CST repair)

**tester_ca evidence (follow-up):**

- **Scope:** `add_fallback_logic.py` only; explicit **E265**, **E402**, invalid **mypy** directive, **E303** (via format).
- **Fixed:** Removed bogus shebang-as-comment and preamble so imports follow docstring; removed invalid `# mypy: ignore-errors` line; **`lint_code` → 0** after `format_code`. **`cst_save_tree`** backup `076d9957-b093-4dad-9002-f1574a26b4e2`.
- **Remaining:** **`type_check_code`** → **1** × **`no-untyped-def`** on `add_fallback_logic_to_file` (~L18). Blocked under strict MCP-only: **`replace_file_lines`** rejected (**`USE_CST_COMMANDS`**); fragment **`cst_modify_tree`** on signature rejected (**`INVALID_OPERATION`**); full **`FunctionDef` replace** preview showed unsafe escape/brace drift — **not applied**.
- **Next recommended batch:** Either **`coder_auto`** enables one-shot line edit for healthy files / improves literal-preserving replace, **or** orchestrator approves a **narrow server config** exception; else **`# type: ignore[no-untyped-def]`** on that `def` if policy allows (still via CST on **`SimpleStatementLine`** if parseable).
