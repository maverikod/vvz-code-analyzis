<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Global Implementation Plan

## Overview

This plan restores reachability of `code-analysis-server` through `mcp-proxy`, where `mcp-proxy` itself runs over mTLS, and aligns the same network/mTLS model for dependent services such as the vectorizer and chunker before any further `vast_srv` work resumes.

## Global Steps

1. Determine the exact runtime, certificate, registration, and dependent-service connectivity path required to expose `code-analysis-server` through `mcp-proxy`, where `mcp-proxy` runs over mTLS, for the Docker network host context `smart-assistant`.
2. Apply the minimal configuration and startup changes needed to run and register `code-analysis-server` through `mcp-proxy`, and align any required vectorizer/chunker connectivity assumptions.
3. Verify proxy discovery, command reachability, and dependent-service connectivity, then declare the resume checkpoint for the `vast_srv` server-only workflow.
4. After live confirmation of `C0` in the current environment, begin `C1` for `vast_srv`: resolve project identity and confirm server-only access to the project through `code-analysis-server`, using `tester_ca` only for guarded paths.
5. After `C1` succeeds, perform the initial server-only analysis pass on `vast_srv` to build the first validated defect backlog: explicit errors, unfinished code, and logical duplicates.
6. Before opening the broad fix phase, investigate the `vast_srv` coverage gap and monitor analysis dynamics over time to determine whether skipped files are still being processed, intentionally filtered, or blocked by a server-side limitation or defect.
7. If Step 6 identifies a `code-analysis-server` analysis-path limitation or defect, repair that server-side issue first, then re-run `C0`, `C1`, and `C2` before reopening any broader `vast_srv` work.
8. If the repaired analysis path still reports implausible `comprehensive_analysis` coverage summary values, investigate and repair the server-side summary/counting logic before opening the broad `vast_srv` fix phase.
9. After coverage summary reliability is revalidated, begin the broad `vast_srv` fix phase under server-only execution, prioritizing explicit errors first, then unfinished code, then logical duplicates.
10. If the `vast_srv` fix phase encounters a server-side CST editing defect that blocks safe server-only fixes, repair that `code-analysis-server` editing defect first, then resume the interrupted `vast_srv` batch from the last successful checkpoint.

## Dependency Order

Step 1 blocks Step 2. Step 2 blocks Step 3.
Step 3 blocks Step 4.
Step 4 blocks Step 5.
Step 5 blocks Step 6.
Step 6 blocks Step 7 when a server-side issue is identified.
Step 7 blocks Step 8 when post-repair coverage summaries remain unreliable.
Step 8 blocks Step 9 until coverage summary reliability is revalidated.
Step 9 blocks Step 10 when a server-side CST editing defect blocks safe continuation.

## Resume Rule

If Step 2, Step 3, Step 4, Step 5, or Step 6 reveals a defect in `code-analysis-server`, stop, fix the defect, re-verify server registration and current project access, and resume from the last successful global checkpoint.
If Step 7 is opened, no broader `vast_srv` fix work may proceed until the repaired server re-passes `C0`, `C1`, and `C2`.
If Step 8 is opened, no broader `vast_srv` fix work may proceed until coverage summary reliability is revalidated.
Step 9 must continue to use server-only `vast_srv` access, with guarded-path execution only through `tester_ca`.
If Step 10 is opened, the interrupted `vast_srv` batch may resume only after the server-side editing defect is repaired and the relevant server-only fix path is revalidated.
