# Implementation plan: Mutable CST layer

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com  

**Context:** [MUTABLE_CST_LAYER_TZ.md](MUTABLE_CST_LAYER_TZ.md) — full specification. Principle: **1 step = 1 file**. Each step is in its own file under [steps/](steps/).

**Execution order:** 00 → 01 → 02 → 03 → 04 → 05 → 06 → 07 (linear; each step depends on the previous).

---

## Mandatory checks after each code step

After writing or changing any code file in a step:

1. **Search and fix**
   - Incomplete code
   - TODO, FIXME
   - Ellipsis (`...`) and syntax violations
   - `pass` outside exception bodies
   - `NotImplemented` outside abstract methods
   - Deviations from project rules or this plan/TZ
2. **Tools**
   - `code_mapper -r code_analysis` and fix all reported errors
   - `black`, `flake8`, `mypy` on touched files; fix all issues

---

## Steps (1 step = 1 file)

| Step | File | Description |
|------|------|-------------|
| [Step 00](steps/step_00_design.md) | Design doc | Mutable node model, conversion, edits, serialization (no code) |
| [Step 01](steps/step_01_package_init.md) | `code_analysis/core/mutable_cst/__init__.py` | Package init, exports |
| [Step 02](steps/step_02_models.md) | `code_analysis/core/mutable_cst/models.py` | Mutable node and tree model |
| [Step 03](steps/step_03_build.md) | `code_analysis/core/mutable_cst/build.py` | Build from LibCST |
| [Step 04](steps/step_04_edits.md) | `code_analysis/core/mutable_cst/edits.py` | Replace, insert, delete in place |
| [Step 05](steps/step_05_serialize.md) | `code_analysis/core/mutable_cst/serialize.py` | Serialize to source (and optionally to LibCST) |
| [Step 06](steps/step_06_integration.md) | `code_analysis/core/cst_tree/tree_modifier.py` | Batch path uses mutable layer |
| [Step 07](steps/step_07_tests.md) | `tests/test_mutable_cst_layer.py` | Unit and integration tests |

---

## Dependencies

- 01 depends on 00
- 02 on 01
- 03 on 02
- 04 on 02, 03
- 05 on 02, 04
- 06 on 02–05
- 07 on 02–06

No parallelisation: run steps in order.

---

## Final gate

After all steps:

- Run full test set for CST/tree modifier and mutable layer.
- Run black, flake8, mypy on all touched files.
- Re-read [MUTABLE_CST_LAYER_TZ.md](MUTABLE_CST_LAYER_TZ.md) and confirm §5 Acceptance criteria and §9 Checklist are satisfied.
