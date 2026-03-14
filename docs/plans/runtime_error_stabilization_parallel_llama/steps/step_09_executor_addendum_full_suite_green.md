# Step 09 — Executor addendum: full suite green

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Step:** [step_09_fix_vectorization_unpack_in_processing.md](step_09_fix_vectorization_unpack_in_processing.md)  
**Plan:** [../plan/PLAN.md](../plan/PLAN.md)

---

## Purpose

Step 09 was not accepted because the **full test suite was not green** (76 collection/runtime errors). This addendum gives the executor **mandatory actions** so that step 09 can be re-validated and accepted under the plan’s completion condition (full suite green).

---

## Root causes of the 76 errors (orchestrator analysis)

1. **Pytest collection scope**  
   The repo has **no** root `pytest.ini` or `pyproject.toml` with `testpaths`. If pytest is run from repo root **without** an explicit path (e.g. `pytest`), it collects the **current directory and all subdirs**, including `test_data/`. Under `test_data/vast_srv/` there are many `test_*.py` files (and nested `tests/`). Pytest loads them as test modules; those modules import dependencies (e.g. `torch`, or packages from vast_srv’s own venv) that are **not** in the code_analysis project’s `.venv` → **ModuleNotFoundError** during collection. So the 76 errors are largely **collection errors** from wrong scope, not from step_09 code.

2. **Connection errors (e.g. ConnectionRefused, localhost)**  
   Some tests (e.g. pipeline MCP, integration) need a running DB driver socket and/or MCP server. If they are run without those services, they fail with connection errors. For step 09, the **canonical** full-suite run must use a command that either: (a) restricts to `tests/` only and, if needed, (b) clearly defines which tests require services so they can be skipped or the services started.

3. **“torch” missing**  
   Not a dependency of this repo; it appears when pytest collects and imports Python files from `test_data/vast_srv/`, which have their own environment.

---

## Mandatory actions for the executor

### 1. Fix full-suite scope (required)

- **Add root-level pytest configuration** so that the **only** collected tree is `tests/`.
  - Either create `pytest.ini` in the **repository root** with:
    - `testpaths = tests`
    - Optionally `norecursedirs` so that even if someone runs `pytest` with no path, `test_data` and other non-test dirs are not collected (or rely on `testpaths` only).
  - Or add a root `pyproject.toml` with a `[tool.pytest.ini_options]` section setting `testpaths = ["tests"]`.
  - **Rule:** Do not collect `test_data/` or any path outside `tests/` for the code_analysis test suite.
- **Canonical full-suite command** (to be used for “full suite green” and in step/plan docs):
  - From repo root, with `.venv` activated:
  - `pytest tests/ -q`
  - Or, if config uses `testpaths = tests`: `pytest -q` (same effect).
- **Update step_09 description** so that the Validation section explicitly states:
  - “Full suite” means: `pytest tests/ -q` (or the single canonical command from root config).
  - Completion: no collection errors, no test failures (green).

### 2. Re-run and classify remaining failures

- After (1), run the canonical full-suite command.
- If there are **still** failures:
  - **Collection errors:** Fix any remaining collection/import issues (e.g. in `tests/` or in conftest) so that `pytest tests/` collects with zero errors.
  - **Runtime failures:**  
    - If they are **integration/service-dependent** (DB socket, MCP server, embedding, etc.): either document that step_09 “full suite green” is defined as “all tests in `tests/` that do not require external services pass when those services are down” and exclude/skip the service-dependent tests by default, **or** document that “full suite green” requires starting the needed services before running. Do **not** leave the plan’s “full suite green” undefined.
    - If they are **regressions** (e.g. related to `processing.py` or vectorization): fix the code or fixtures so the tests pass.

### 3. No scope creep

- Do **not** change the **behavior** of `processing.py` beyond what step_09 specifies (unpack of `ensure_database_connection()` and propagation of `db_status_logged`).
- Do **not** add new production code except: (a) root pytest config (ini or pyproject), and (b) any minimal change in `tests/` or conftest **only** to make collection correct (e.g. excluding dirs, fixing an import that breaks collection). No new features.

### 4. Validation checklist (all must pass)

- [ ] Root pytest config exists and restricts collection to `tests/` (and does not collect `test_data/`).
- [ ] `pytest tests/ -q` from repo root (with `.venv`) runs with **zero collection errors**.
- [ ] Same run: **all tests pass** (green), or the plan/step explicitly defines which tests are excluded when services are down and those are the only skips.
- [ ] `black`, `flake8`, `mypy` on any modified file (including new config file if it’s Python) pass.
- [ ] Step_09 description file updated with the exact full-suite command and completion criterion.

---

## Summary

- **Primary fix:** Restrict pytest to `tests/` only (root config + canonical command `pytest tests/ -q`).
- **Then:** Re-run full suite; resolve any remaining collection or runtime failures; document or skip service-dependent tests so that “full suite green” is unambiguous.
- **Step 09** is done only when the full test suite (as defined above) is green and the checklist is satisfied.
