# Hardware Pentest Agent — Agent Instructions

This repository controls real security hardware. Treat the runtime, policy engine, preflight, verification store, evidence model, and typed adapters as enforcement boundaries. Do not bypass them to make a test pass.

## Default development workflow

Run the named harness profiles instead of inventing ad-hoc commands:

```bash
python scripts/test_harness.py quick
python scripts/test_harness.py contract
python scripts/test_harness.py ci
```

`quick`, `contract`, and `ci` must not require real hardware. Before opening or merging a PR, run `python scripts/test_harness.py ci`.

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
- Never bypass engagement policy, approval, human-action, preflight, or hardware-verification gates.
- Never mark a capability `hardware_verified` from mocks, simulator output, or recorded transcripts.
- Do not transmit RF/Wi-Fi/IR traffic unless the requested test is explicitly classified for transmission and the operator has enabled the required approval path.
- Do not use active deauthentication, credential-harvesting portals, BadUSB/HID injection, destructive storage operations, or arbitrary generated FAP execution as a shortcut.
- Wi-Fi credentials belong in environment variables or secret references, never persisted Action inputs, transcripts, fixtures, logs, or evidence.
- Generated FAPs must remain in the reserved `hpa_gen_` / `NullSquare` namespace and go through synthesis policy, immutable provenance, bounded execution, and cleanup.

## Test expectations

New transport or hardware-facing code should add at least one negative/fault test for the relevant failure boundary: malformed response, partial write, disconnect/read error, timeout, stale identity, changed firmware, tampered evidence/artifact, cleanup failure, or unsafe input rejection.

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

When no route exists, prefer capability composition or the policy-gated synthesis pipeline; do not add a raw command escape hatch.
