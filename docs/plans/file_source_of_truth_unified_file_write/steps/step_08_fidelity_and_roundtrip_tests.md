# Step 08: Fidelity and Round-Trip Test Suite

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Role

Senior Python test engineer.

## Target code file

`tests/test_file_tree_snapshot_fidelity.py`

## Goal

Add end-to-end tests that prove full fidelity and unified write behavior.

## Tasks

1. Add tests that prove both flows call the same unified file-level sync function.
2. Add round-trip restore test: index/save -> delete file -> restore from DB -> compare full text.
3. Add sibling order preservation test for reconstructed structure.
4. Add comments/docstrings fidelity tests.
5. Add data-type fidelity tests.
6. Add negative tests for unsafe overwrite behavior.

## Acceptance checks

- All mandatory fidelity conditions are covered and passing.
- Tests fail if sibling order or comments/docstrings are lost.
- Tests fail if write-path unification regresses.

## Blackstops

- Stop if test fixtures require semantic changes to pass.
- Stop if full text equality cannot be guaranteed under defined policy.
