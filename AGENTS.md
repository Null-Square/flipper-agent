# Hardware Pentest Agent — Agent Instructions

This repository controls real security hardware. Treat the runtime, policy engine, engagement store, operator gate store, preflight, verification store, evidence model, typed adapters, and harness-neutral service facade as enforcement boundaries. Do not bypass them to make a test pass.

## Default development workflow

Run the named harness profiles instead of inventing ad-hoc commands:

```bash
python scripts/test_harness.py quick
python scripts/test_harness.py contract
python scripts/test_harness.py ci
```

`quick`, `contract`, and `ci` must not require real hardware. Before opening or merging a PR, run `python scripts/test_harness.py ci`.

## Agent-harness integration

The project owns hardware-pentest domain state and enforcement, not the generic LLM loop. Prefer these boundaries, in order:

1. `hardware_pentest.service.HardwarePentestService` for native Python integration.
2. `hardware-pentest-mcp` for MCP-capable agent harnesses.
3. Existing typed CLI commands for humans, CI, and shell-capable development agents.

Do not create a second implementation of assessment state, engagement scope, policy, preflight, verification, gates, or evidence inside an MCP/HTTP/agent adapter.

Read-only local MCP:

```bash
hardware-pentest-mcp
```

High-level one-step assessment execution for a trusted local harness:

```bash
hardware-pentest-mcp --allow-execution
```

A local HTTP endpoint may be started explicitly:

```bash
hardware-pentest-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

HTTP execution additionally requires `HPA_MCP_REMOTE_EXECUTION=1`. The built-in launcher intentionally refuses non-loopback binding. Do not weaken either guard to make remote testing easier. Use a secure MCP tunnel or a separately authenticated deployment layer.

## Operator-owned actions

Agents must not import/expand their own engagement scope or satisfy their own approval, physical-action, or recovery gates through MCP.

Operator scope is imported separately:

```bash
hardware-pentest-operator engagement-import --manifest ./engagement.yaml
```

One-shot gates are created only through the interactive operator CLI:

```bash
hardware-pentest-operator gate-grant \
  --assessment-id <assessment> \
  --step-id <exact-step-id> \
  --kind approval
```

Gate kinds are `approval`, `human_action`, and `recovery`. `gate-grant` requires an interactive TTY and exact step-ID confirmation. Never add an MCP `gate_grant`, `approve=true`, `human_action_complete=true`, or equivalent self-approval shortcut.

## Real hardware

Real hardware tests are opt-in only. Never open a serial device merely because one is discoverable.

The operator must explicitly export:

```bash
export HPA_HIL=1
export HPA_FLIPPER_PORT=/dev/...
export HPA_MARAUDER_PORT=/dev/...   # when the Marauder board is part of the test
```

Then use:

```bash
python scripts/test_harness.py hil
```

Do not run HIL when `HPA_HIL` is absent or not `1`.

### Safe local commands

These are preferred for inspecting an attached stack:

```bash
hardware-pentest flipper-ports
hardware-pentest flipper-probe --port "$HPA_FLIPPER_PORT"
hardware-pentest flipper-self-test --port "$HPA_FLIPPER_PORT"
hardware-pentest-preflight --flipper-port "$HPA_FLIPPER_PORT" --marauder-port "$HPA_MARAUDER_PORT"
```

Use high-level typed CLI commands and adapters. Do not open pyserial directly from an agent-created scratch script when the repository already has a typed transport for that operation.

## Safety invariants

- Never expose a generic Flipper CLI or generic Marauder command surface to the assessment agent.
- Never expose a generic serial-write or shell escape through MCP or another remote interface.
- Never bypass engagement policy, approval, human-action, recovery, preflight, or hardware-verification gates.
- Never mark a capability `hardware_verified` from mocks, simulator output, or recorded transcripts.
- Do not transmit RF/Wi-Fi/IR traffic unless the requested test is explicitly classified for transmission and the operator has enabled the required approval path.
- Do not use active deauthentication, credential-harvesting portals, BadUSB/HID injection, destructive storage operations, or arbitrary generated FAP execution as a shortcut.
- Wi-Fi credentials belong in environment variables or secret references, never persisted Action inputs, transcripts, fixtures, logs, evidence, or compact agent context.
- Generated FAPs must remain in the reserved `hpa_gen_` / `NullSquare` namespace and go through synthesis policy, immutable provenance, bounded execution, and cleanup.
- Network exposure must not change capability semantics, action classes, or approval requirements.
- Hosted/production agents should receive MCP tools only, not shell access on the hardware host.

## Test expectations

New transport or hardware-facing code should add at least one negative/fault test for the relevant failure boundary: malformed response, partial write, disconnect/read error, timeout, stale identity, changed firmware, tampered evidence/artifact, cleanup failure, or unsafe input rejection.

New harness interfaces must prove that they expose high-level domain operations only, do not expose operator gate creation, and refuse unsafe network exposure by default.

Protocol fixtures and contract tests may model real device output, but must be sanitized. Secrets, stable user identifiers, and unrelated device data must not be committed.

## Architecture

Reason in capabilities, not device commands:

```text
assessment objective
  -> TestCase
  -> capability
  -> registry/router
  -> policy/approval/human action
  -> instrument adapter
  -> evidence
  -> observation
  -> finding only after validation
```

The outer agent harness may own model inference, generic conversation context, and its tool loop. Durable pentest context must come from the runtime, especially `assessment_context`, rather than being trusted to model memory.

When no route exists, prefer capability composition or the policy-gated synthesis pipeline; do not add a raw command escape hatch.
