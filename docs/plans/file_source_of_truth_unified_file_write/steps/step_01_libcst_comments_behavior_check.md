# Step 01: LibCST Comments Behavior Check (Blocking)

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Role

Senior Python developer and test engineer.

## Target code file

`tests/test_libcst_comment_behavior.py`

## Goal

Create a blocking verification suite that proves how LibCST handles:

- inline comments,
- standalone comments,
- end-of-line comments,
- module/class/function docstrings,
- mixed comment + docstring round-trip.

## Tasks

1. Add tests that parse and regenerate code via LibCST.
2. Assert comments are preserved in round-trip text output.
3. Assert docstrings are preserved in round-trip text output.
4. Add a negative guard: no silent conversion of comments into docstrings.
5. Document discovered behavior in test names/messages.

## Acceptance checks

- Tests clearly prove whether fallback conversion is needed.
- If comments are preserved by LibCST, mark fallback conversion as prohibited in normal flow.

## Blackstops

- Stop if tests indicate unstable comment preservation and no deterministic workaround exists.
- Stop if test fixtures require normalization that changes semantics.
