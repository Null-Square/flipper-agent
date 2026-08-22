# Capability Model

## Purpose

The capability model separates security intent from instrument implementation.

Assessment logic requests a capability. The runtime selects an instrument that can provide it.

## Naming

Use stable dotted identifiers.

Pattern:

```text
<surface>.<technology-or-interface>.<operation>
```

Examples:

```text
wireless.nfc.identify
wireless.nfc.observe
wireless.rfid.identify
wireless.subghz.observe
infrared.observe
internal.uart.observe
internal.spi.capture
internal.i2c.capture
debug.jtag.detect
debug.swd.detect
memory.acquire
firmware.extract
firmware.analyze
protocol.decode
evidence.capture
```

Do not include a vendor or product name in a core capability identifier.

Bad:

```text
flipper.nfc.read
proxmark.hf.search
```

Those names belong inside adapter implementation details.

## Capability descriptor

Each capability descriptor contains:

```text
id
description
surface
operation
action_class
input_schema
output_schema
prerequisites
constraints
evidence_types
maturity
quality
instrument_id
adapter_id
```

## Maturity

Use these states:

- `declared`;
- `simulated`;
- `implemented`;
- `hardware_verified`;
- `assessment_verified`.

The public runtime must not report a capability as working only because it is declared in code.

## Quality metadata

Different instruments can implement the same capability with different depth.

A descriptor may include:

- fidelity;
- confidence;
- speed class;
- passive/active behavior;
- supported protocols;
- input limits;
- output detail;
- known limitations.

The first router can use simple deterministic priority. Later routing can account for quality metadata.

## Capability request

A capability request contains:

```text
capability_id
target_id
test_case_id
required_constraints
preferred_instrument
normalized_inputs
```

`preferred_instrument` is advisory unless the assessment explicitly requires one instrument.

## Routing example

Available instruments:

```text
Flipper Zero
  wireless.nfc.identify
  wireless.rfid.identify

Proxmark3
  wireless.nfc.identify
  wireless.rfid.identify
  wireless.nfc.deep_analyze
```

Request:

```text
wireless.nfc.identify
```

Both instruments qualify.

The router can prefer Flipper for a fast passive observation and reserve Proxmark3 for deeper follow-up work.

This policy belongs in routing metadata, not the test case.

## Action model

A capability resolves into a typed action.

Example:

```json
{
  "action_id": "act-001",
  "capability_id": "wireless.nfc.identify",
  "target_id": "smart-lock-a",
  "action_class": "OBSERVE",
  "inputs": {
    "timeout_seconds": 15
  }
}
```

The action must validate before execution.

## Result model

An adapter returns an execution result.

Example shape:

```json
{
  "status": "success",
  "instrument_id": "flipper-abc123",
  "capability_id": "wireless.nfc.identify",
  "raw": {},
  "normalized": {},
  "artifacts": [],
  "limitations": []
}
```

The adapter returns data. It does not decide whether the result is a vulnerability.

## Initial capability groups

### Wireless

```text
wireless.nfc.identify
wireless.nfc.observe
wireless.rfid.identify
wireless.rfid.observe
wireless.subghz.observe
```

### Infrared

```text
infrared.observe
```

### Internal interfaces

```text
internal.gpio.inspect
internal.uart.detect
internal.uart.observe
internal.spi.capture
internal.i2c.capture
```

### Debug

```text
debug.jtag.detect
debug.swd.detect
debug.session.open
```

### Memory and firmware

```text
memory.acquire
firmware.extract
firmware.analyze
firmware.emulate
```

### Protocol analysis

```text
protocol.decode
protocol.characterize
```

### Evidence

```text
evidence.capture
```

The list is a design seed. Add capabilities only when a real test case or instrument integration requires them.

## Capability registration

An adapter registers capabilities after it probes the connected instrument.

Registration must consider:

- actual device model;
- firmware/tool version;
- available transport;
- installed extensions where relevant;
- configuration;
- capability maturity.

Do not advertise a theoretical capability that the current connection cannot execute.

## Capability discovery

The runtime exposes a normalized inventory:

```text
Instrument: Flipper Zero
Transport: USB
Status: ready
Capabilities:
  wireless.nfc.identify        hardware_verified
  wireless.rfid.identify       hardware_verified
  wireless.subghz.observe      implemented
```

This inventory is what an external agent should consume.

## Capability constraints

Constraints are machine-readable.

Examples:

```text
requires_physical_access
requires_human_setup
requires_voltage_check
receive_only
frequency_min_hz
frequency_max_hz
max_duration_seconds
safe_retry_count
```

The policy and adapter validation layers both use constraints.

## Test-case relationship

A test case requests one or more capabilities.

Example:

```text
TestCase: identify exposed NFC interface
Required capability:
  wireless.nfc.identify
Optional follow-up:
  wireless.nfc.observe
```

The test case must not contain Flipper CLI syntax.

## Instrument adapter rule

Device-specific identifiers remain internal.

The Flipper adapter can map:

```text
wireless.nfc.identify
```

to the correct supported RPC/CLI implementation.

A Proxmark adapter can map the same capability to its own client interface.

Assessment code does not change.

## Versioning

Capability identifiers should be stable.

If semantics change incompatibly, create a versioned schema or a new capability identifier rather than silently changing meaning.

Adapters can evolve independently from capability identifiers.

## Acceptance

The capability model is proven when:

- the simulator and Flipper adapter implement the same capability contract;
- the planner does not contain device-specific command strings;
- unavailable capabilities cannot be planned as executable steps;
- capability metadata drives policy and routing;
- a second instrument can register an overlapping capability without changing existing test cases.
