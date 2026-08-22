# Flipper USB Transport

## Purpose

Milestone 1 establishes a verified host-to-Flipper control path before the runtime exposes any physical assessment capability.

## Current transport

The first implementation uses the stock Flipper USB CDC command-line interface (CLI).

The official firmware exposes a CLI prompt of `>: ` and supports `info device` for device identity. The official USB CDC descriptor uses vendor ID `0x0483` and product ID `0x5740`. Port discovery treats USB metadata as a hint only. The adapter must complete the identity handshake before the runtime registers the instrument.

The host sets the serial baud rate to `230400`, which matches current Flipper user documentation. USB CDC is a virtual serial link, so the firmware implementation does not depend on the physical UART baud rate.

## Identity handshake

The adapter performs this sequence:

1. Open a bounded USB CDC session.
2. Wait for the CLI prompt.
3. If the prompt is not emitted on connection, send one carriage return and wait again.
4. Send the fixed read-only command `info device`.
5. Parse key/value properties.
6. Require `hardware_model: Flipper Zero` or the equivalent dotted key shape.
7. Capture UID and firmware version when present.
8. Close the probe session.

A USB port name or VID/PID match is not sufficient identity evidence.

## Safety boundary

The transport has no public raw-command method.

Higher layers must implement typed operations. Each typed operation must validate its inputs before it reaches the private CLI execution method.

Milestone 1 does not advertise NFC, RFID, Sub-GHz, infrared, GPIO, UART, or other pentest capabilities. Those capabilities move into the registry only after implementation and hardware verification.

## Timeouts and failures

All prompt and command waits are bounded. The transport maps failures into typed errors for:

- missing optional dependencies;
- open/read/write failures;
- timeouts;
- malformed responses;
- identity mismatch.

The adapter closes the serial handle after failed initialization.

## RPC direction

The stock firmware also supports `start_rpc_session`, which switches the CLI transport to the official protobuf RPC protocol. The official protobuf schema exposes system device information, storage, application, GUI, GPIO, desktop, and related RPC messages.

RPC is the preferred structured path where it adds clear value. It will be introduced behind the same transport/adapter boundary rather than exposed directly to the agent. CLI remains a typed fallback for operations that do not have a suitable RPC surface.

## Hardware verification

CI verifies the transport with deterministic fake serial fixtures. Real hardware verification remains required before Milestone 1 is complete.

The `flipper-self-test` command opens two independent read-only CLI sessions. It confirms that the Flipper identity, transport, and firmware metadata remain stable. It can also write a JSON verification record that can be attached to the milestone evidence.

The real-device checklist is:

1. Install the project with the `flipper` extra.
2. Connect a stock or supported Flipper Zero by USB.
3. Close qFlipper or other programs that own the serial device.
4. Run `hardware-pentest flipper-ports`.
5. Run `hardware-pentest flipper-probe --port <PORT>`.
6. Run `hardware-pentest flipper-self-test --port <PORT> --output verification.json`.
7. Confirm the self-test reports `passed: true`.
8. Disconnect the device and confirm the probe fails safely.
9. Reconnect and repeat the self-test.

Record the firmware version, host operating system, and generated verification record when the hardware test is performed.
