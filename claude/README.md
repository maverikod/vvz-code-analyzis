# code-analyzis Claude prompt package

`../CLAUDE.md` is the entrypoint. This directory contains the project-bound
Claude contract bundle.

Package version: `v1.6.8`

## Layout

- `modes.yaml`: mode router.
- `roles/common.yaml`, `roles/laws.yaml`, `roles/tooling.yaml`, `roles/orchestrator.yaml`: mandatory core read.
- `roles/*.yaml`: stage contracts.
- `ops/*.yaml`: lazily loaded operating cards.
- `VERSION`: bundle version marker.

## Project bindings

- Project: `code-analyzis`
- Local checkout: `/home/vasilyvz/projects/tools/code_analysis`
- CAS project ID: `44a8ce88-b467-42a8-b874-033562b89bd0`
- CAS server: `code-analysis-server-vvz`

## Notes

- This bundle is Claude-only.
- Codex prompt files remain outside this directory and are not modified by it.
- Relative bundle references resolve from `claude/`.
