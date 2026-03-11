# Sandbox Adoption Plan (2026-02)

## Goal

Deliver security posture improvements without increasing default onboarding friction.

## Policy

- Keep default `sandbox.mode=off`.
- Make sandbox opt-in simple (`setup --enable-sandbox`) and diagnosable (`doctor sandbox`).

## Completed scope (P0/P1)

1. `doctor sandbox` diagnostics:
- Docker CLI/runtime checks
- configured sandbox mode check
- image readiness check
- mount allowlist visibility check

2. setup fast path:
- `drugclaw setup --enable-sandbox` updates config directly
- setup wizard default remains sandbox disabled

3. execution policy engine:
- `host-only` / `sandbox-only` / `dual` labels
- pre-execution policy validation with explicit block error type

4. path and mount hardening:
- sensitive path blocking
- symlink validation
- external allowlist support for mount/path controls

5. web security posture panel:
- config self-check now returns posture payload
- UI shows sandbox/runtime/allowlist state and policy tags

## Next checkpoints

1. Add usage metrics for policy-block events and sandbox fallback events.
2. Expand `sandbox-only` coverage to selected high-risk tools after compatibility tests.
3. Add CI security regression suite for traversal/symlink/cross-chat access scenarios.
