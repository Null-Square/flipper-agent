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

Normal runtime discovery resolves verification records from the evidence-backed verification store. Explicit capability-name overrides are restricted to tests/development and require an opt-in flag.

## Current capability table

| Capability | Action class | Code state | Agent-visible by default | Hardware evidence |
|---|---|---|---|---|
| `infrared.observe` | `OBSERVE` | implemented | no | pending |
| `wireless.subghz.observe` | `OBSERVE` | implemented | no | pending |
| `wireless.nfc.identify` | `INTERACT` | implemented | no | pending |
| `internal.gpio.inspect` | `OBSERVE` + human setup | implemented | no | pending |

## `infrared.observe`

Purpose: receive and normalize infrared signals without transmitting.

The implementation uses `ir rx` or `ir rx raw`. The runtime starts a bounded capture window and sends Ctrl+C (ETX) to stop the stock receive loop.

Inputs:

- `duration_seconds`: `0.01` to `30.0` seconds;
- `raw`: boolean, default `false`.

If no signal arrives, the result is `INCONCLUSIVE`.

## `wireless.subghz.observe`

Purpose: receive and normalize decodable Sub-GHz packets without transmitting.

The implementation uses the stock receive command with the internal CC1101 radio only:

```text
subghz rx <frequency_hz> 0
```

The runtime accepts frequencies inside the receive ranges defined by the current stock firmware:

- `299999755` to `348000000` Hz;
- `386999938` to `464000000` Hz;
- `778999847` to `928000000` Hz.

Inputs:

- `duration_seconds`: `0.01` to `30.0` seconds;
- `frequency_hz`: integer, default `433920000`.

The normalized output preserves the tuned frequency, radio index, decoded protocol name, and protocol fields reported by the stock Flipper decoder.

If no decodable packet arrives, the result is `INCONCLUSIVE`.

## `wireless.nfc.identify`

Purpose: identify NFC protocol families without reading application data, writing a tag, or emulating one.

The implementation enters the stock NFC CLI and invokes only:

```text
scanner -t
```

The tree output is normalized into protocol hierarchies such as:

```text
ISO14443-3A -> Mifare Ultralight
```

Inputs:

- `duration_seconds`: `0.01` to `30.0` seconds.

This capability is classified as `INTERACT`, not `OBSERVE`. NFC identification requires the reader field and protocol exchange to discover nearby tags, so calling it passive would be misleading even though the operation is non-destructive.

If no NFC protocol is identified during the bounded scan window, the result is `INCONCLUSIVE`.

## `internal.gpio.inspect`

Purpose: read one already-prepared digital input on the Flipper external header without driving the target.

The runtime invokes only:

```text
gpio read <PIN>
```

It does **not** invoke `gpio mode`, `gpio set`, or any output operation.

Supported MVP pins are the normal non-debug external GPIO pins from the stock F7 resource table:

- `PA7`
- `PA6`
- `PA4`
- `PB3`
- `PB2`
- `PC3`
- `PC1`
- `PC0`

Debug/special-purpose pins such as SWD, UART, iButton, speaker, and IR-TX pins are excluded from this capability.

This operation is `OBSERVE` because it only reads the digital level, but every action must set `requires_human_action=true`. Before the target is connected, the operator must:

1. choose one of the supported non-debug pins;
2. configure that pin as an input using the trusted local Flipper setup workflow;
3. confirm a common ground;
4. confirm the target signal voltage is safe for the Flipper Zero input;
5. only then connect the target signal.

The agent never performs those physical/electrical setup steps itself. If the pin is not already in input mode, the stock firmware refuses the read and the capability fails without attempting to change the mode.

Inputs:

- `pin`: one of the eight supported non-debug pin names.

A successful result preserves the pin name and digital level (`0` or `1`). It does not infer protocol semantics from one level sample.

## Verification gate

The normal Flipper adapter resolves verified capabilities through the local verification store. Verification is bound to the exact instrument identity, firmware version, and adapter version, and retained evidence is re-hashed when capabilities are resolved.

This means:

- unit tests can exercise implemented operations with deterministic fake hardware;
- development code can exist before hardware verification;
- normal capability discovery cannot expose an unverified operation by accident;
- firmware or adapter changes invalidate previous capability verification until it is repeated;
- a later failed verification revokes an earlier successful verification for the same state.

See `docs/HARDWARE_VERIFICATION.md` for the trust model.

## Out of scope

The current capabilities do not implement:

- infrared transmit or replay;
- Sub-GHz transmit or replay;
- NFC tag data extraction beyond protocol identification;
- NFC writes, cloning, or emulation;
- GPIO mode changes or output writes during an assessment action;
- debug/special-purpose GPIO access;
- brute force;
- universal remote actions;
- external CC1101 selection;
- arbitrary CLI command execution.
