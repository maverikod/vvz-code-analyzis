<!--
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
-->

# Technical Specification

## Assignment

Restore a working `code-analysis-server` runtime and MCP proxy registration through `mcp-proxy`, where the proxy itself operates over mTLS, and ensure the same network and mTLS compatibility model is correct for dependent external services including the vectorizer and chunker, so the server is reachable from the Docker network host context named `smart-assistant`, then resume the server-only `vast_srv` development workflow.

## Goals

1. Start `code-analysis-server` successfully.
2. Bind or advertise it through the host/addressing model required by the Docker network context `smart-assistant`.
3. Ensure the server is registered and reachable through `mcp-proxy`, which operates over mTLS.
4. Ensure the same mTLS and host-addressing assumptions are correct for dependent external services used by the flow, especially the vectorizer and chunker.
5. Preserve the main campaign rule: no work on `vast_srv` may use anything except `code-analysis-server` tools.
6. If a defect is found in `code-analysis-server`, stop the interrupted test flow, fix the defect, and resume from the last successful checkpoint.
7. Determine whether server-only analysis coverage for `vast_srv` is complete, still catching up dynamically, or blocked by a `code-analysis-server` limitation or defect before opening the wider fix phase.

## Non-Goals

1. No direct work on `vast_srv` in this step.
2. No speculative cleanup or development on `vast_srv` before proxy reachability is confirmed.
3. No bypass of proxy registration using direct local-only validation as a substitute for MCP reachability.
4. Tactical work must treat `mtls_certificates/` as the certificate/material location used by `mcp-proxy` and any dependent mTLS-enabled external services in this chain when determining correct registration and host binding.

## Constraints

1. Global orchestration may delegate only through `orchestrator_tactical`.
2. Any future read/write/analyze/verify of `test_data/vast_srv` must use `tester_ca` only through MCP to `code-analysis-server`.
3. If required tooling or capabilities are missing, execution must stop and report the exact blocker.
4. `mcp-proxy-adapter` may be updated or configured with ordinary repository tooling if needed for registration, but this does not relax the `vast_srv` rule.

## Required Outcome

The environment must reach a state where:

1. `code-analysis-server` is running.
2. `mcp-proxy` can discover it while running in its mTLS configuration.
3. Proxy-mediated command calls succeed against it through `mcp-proxy`.
4. The effective address/binding is compatible with the Docker network host context `smart-assistant`.
5. The certificate/config path used by the proxy registration is aligned with `mtls_certificates/`.
6. Any required vectorizer and chunker connectivity assumptions are aligned with the same `smart-assistant` and mTLS model.

## Acceptance Criteria

1. Tactical execution identifies the exact config, runtime path, certificate usage, and host binding changes required for `mcp-proxy` running over mTLS for `smart-assistant`, and the equivalent assumptions for vectorizer and chunker dependencies.
2. Tactical execution applies only the necessary changes to start and register `code-analysis-server`.
3. Tactical verification proves that `mcp-proxy` now lists `code-analysis-server`.
4. Tactical verification proves that at least one minimal command and one schema/help-style call succeed through `mcp-proxy` against `code-analysis-server`.
5. Tactical verification proves that any required vectorizer and chunker dependencies are reachable under the same network and mTLS assumptions, or explicitly reports them as blockers.
6. Tactical reporting explicitly states the checkpoint from which the `vast_srv` campaign can resume.
7. Before broad `vast_srv` fixes begin, tactical reporting must be able to distinguish between delayed analysis coverage growth and a real server-side coverage problem.
