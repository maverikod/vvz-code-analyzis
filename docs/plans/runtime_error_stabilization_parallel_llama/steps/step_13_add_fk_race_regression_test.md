# Step 13: Add FK-race regression test

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Target file

`tests/regression/test_index_file_fk_race_guard.py`

## Task

Add regression tests for race-safe behavior when indexing is requested for a deleted/missing project:

1. Missing project_id path returns deterministic error result (no crash).
2. No FK exception escapes to top-level test failure.
3. Valid project path still succeeds.

Tests should use project fixture setup/teardown and avoid flaky timing.

## Validation

- `black tests/regression/test_index_file_fk_race_guard.py`
- `flake8 tests/regression/test_index_file_fk_race_guard.py`
- `mypy tests/regression/test_index_file_fk_race_guard.py`
- `pytest tests/regression/test_index_file_fk_race_guard.py -q`
- Final: full test suite.

