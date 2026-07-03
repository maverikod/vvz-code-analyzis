# Archive — git-spec plan

## G-001-commit-on-write (excised 2026-07-03)

Excised by explicit user decision on 2026-07-03: commit-on-write behaviour is
out of scope for the git-spec plan. The plan's purpose is limited to adding
`git_*` and `github_*` server commands; the commit-on-write capability block
(global step G-001, its 3 tactical steps, 10 atomic steps, and its 8 owned
machine_spec concepts C-003, C-004, C-005, C-006, C-007, C-008, C-024, C-025)
was removed from the active plan (source_spec.md, spec.yaml,
gs_concept_matrix.yaml, t_concept_matrix.yaml, object_matrix.yaml,
consistency_verification_standard.yaml, tactical_step_creation_standard.yaml)
and archived here in full for historical reference.

The pre-existing `commit_after_write` mechanism in production code
(`code_analysis/core/git_integration.py`) stays untouched by this excision;
only the plan's coverage of it as a distinct capability block was removed.
