# Step 07: Restore Policy and Force Mode

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Role

Senior Python recovery and safety engineer.

## Target code file

`code_analysis/commands/file_management.py`

## Goal

Standardize DB->file restore policy with safe default mode and explicit force overwrite mode.

## Tasks

1. Ensure default restore mode never overwrites existing file.
2. Implement/standardize `force=true` behavior with mandatory backup before overwrite.
3. Keep file-source-of-truth policy intact for non-forced operations.
4. Ensure restored content comes from full stored source/tree payload.

## Acceptance checks

- Existing file + no force => safe refusal.
- Existing file + force => overwrite only after successful backup.
- Missing file + snapshot available => full restoration succeeds.

## Blackstops

- Stop if overwrite can happen without backup in force mode.
- Stop if restore path does not use full stored payload.
