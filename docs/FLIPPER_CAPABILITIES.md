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
| `wireless.subghz.observe` | `OBSERVE` | implemented | no | pending |
| `wireless.nfc.identify` | `INTERACT` | implemented | no | pending |

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

## Verification gate

`FlipperAdapter` accepts an explicit set of verified capability IDs. The default set is empty.

This means:

- unit tests can exercise implemented operations with deterministic fake hardware;
- development code can exist before hardware verification;
- normal capability discovery cannot expose an unverified operation by accident.

Each capability needs a controlled real-device verification before it can be promoted to `hardware_verified` in the runtime configuration path.

## Out of scope

The current capabilities do not implement:

- infrared transmit or replay;
- Sub-GHz transmit or replay;
- NFC tag data extraction beyond protocol identification;
- NFC writes, cloning, or emulation;
- brute force;
- universal remote actions;
- external CC1101 selection;
- arbitrary CLI command execution.
