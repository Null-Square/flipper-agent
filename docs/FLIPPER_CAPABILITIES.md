# Flipper Capability Status

## Rule

A capability can exist in code before the runtime advertises it to an agent.

The Flipper adapter uses this maturity path:

```text
implemented
    -> hardware verified
    -> assessment verified
```

The runtime must not advertise an implemented capability as `hardware_verified` until a real Flipper test produces evidence for that capability.

## Current capability table

| Capability | Action class | Code state | Agent-visible by default | Hardware evidence |
|---|---|---|---|---|
| `infrared.observe` | `OBSERVE` | implemented | no | pending |

## `infrared.observe`

Purpose: receive and normalize infrared signals without transmitting.

The implementation uses the stock Flipper CLI receive command:

```text
ir rx
```

Optional raw observation uses:

```text
ir rx raw
```

The runtime starts a bounded capture window and sends Ctrl+C (ETX) to stop the stock receive loop. It does not call the infrared transmit command.

Inputs:

- `duration_seconds`: `0.01` to `30.0` seconds;
- `raw`: boolean, default `false`.

Normalized decoded observation:

```json
{
  "protocol": "NEC",
  "address": "0x00FF",
  "command": "0x20DF",
  "repeat": false
}
```

If no signal arrives during the capture window, the result is `INCONCLUSIVE`. The runtime must not convert absence of a signal into a security finding.

## Verification gate

`FlipperAdapter` accepts an explicit set of verified capability IDs. The default set is empty.

This means:

- unit tests can exercise implemented operations with deterministic fake hardware;
- development code can exist before hardware verification;
- normal capability discovery cannot expose an unverified operation by accident.

The next hardware step is to run a controlled infrared observation test with a real Flipper and known IR source. After the evidence is recorded, `infrared.observe` can be promoted to `hardware_verified` in the runtime configuration path.

## Out of scope

This capability does not implement:

- infrared transmit;
- replay;
- brute force;
- universal remote actions;
- arbitrary CLI command execution.
