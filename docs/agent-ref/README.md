# `docs/agent-ref/` — Claude agent contracts index

Role-contract layer for **local Claude Code sessions** on this repository.
Entry point: repo-root `CLAUDE.md` (orchestrator contract, imports common + orchestrator).
Cursor keeps its own layer (`.cursor/agents/*.md`, `docs/agents/`); the two do not mix.
Remote agents working through the code-analysis server follow the server-mode
standards named in `roles/tooling.yaml` (access-mode note).

| File | Read by | Contents |
|------|---------|----------|
| `roles/common.yaml` | **every** role, first | universal laws: file-access law, need-to-know zones, escalation chain, spawn protocol |
| `roles/tooling.yaml` | tool-using roles only (researcher, context_former, coder, tester) | manuals map (→ `docs/standards/LOCAL_*`), read-before-act triggers, error taxonomy |
| `roles/orchestrator.yaml` | orchestrator (main model) | decision-only role; delegates all execution |
| `roles/conscience.yaml` | conscience (opus) | adversarial mirror of the orchestrator; verdict only |
| `roles/researcher.yaml` | researcher (sonnet) | read-only code/doc facts for the orchestrator |
| `roles/context_former.yaml` | context_former (sonnet) | builds self-sufficient coder tasks; runs the coder+tester pair |
| `roles/coder.yaml` | coder (haiku, sonnet fallback) | implementation of one inlined task |
| `roles/tester.yaml` | tester (sonnet) | QA gate + tests; verdict straight to coder |

Reading order for any subagent: `common.yaml` → (`tooling.yaml` if tool-using) →
its own `roles/<role>.yaml` → the manuals its role/task names.

Need-to-know: a role never reads another role's file (exception: conscience reads
`orchestrator.yaml` — it is the orchestrator's mirror).

Tool-agnostic law (**CR-017**, `docs/PROJECT_RULES.md`): files in this directory
carry NO mechanics of concrete tools, servers, or proxies — only `manuals` keys
resolved by `tooling.yaml` to standards in `docs/standards/`. Keep it that way
when editing or adding roles.
