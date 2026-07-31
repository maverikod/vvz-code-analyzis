# code-analyzis Codex prompt package

`../AGENTS.md` is the entrypoint. This directory contains the project-bound
Codex contract bundle.

Package version: `v1.6.13`

## Layout

- `modes.yaml`: mode router.
- `roles/common.yaml`, `roles/laws.yaml`, `roles/orchestrator.yaml`: mandatory core read.
- `roles/*.yaml`: stage contracts.
- `ops/*.yaml`: lazily loaded operating cards, including cheapest-capable model selection.
- `VERSION`: bundle version marker.

## Project bindings

- Project: `code-analyzis`
- Local checkout: `/home/testuser/projects/code-analyzis`
- CAS project ID: `44a8ce88-b467-42a8-b874-033562b89bd0`
- CAS server: `code-analysis-server-vvz`

## Notes

- This bundle is Codex-only.
- Claude prompt files remain outside this directory and are not modified by it.
- Relative bundle references resolve from `codex/`.
