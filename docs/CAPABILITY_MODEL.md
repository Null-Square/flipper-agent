# Capability Model

## Purpose

The capability model separates **security intent** from **physical implementation**.

Assessment logic asks for a capability. The runtime determines how that capability can be satisfied using the available hardware providers.

The key distinction is:

```text
Capability = what physical/security operation is required
CapabilityImplementation = one concrete way to perform it
HardwareProvider = the board/tool that can host or execute that implementation
```

This allows the same capability to be built into one tool, synthesized on another board, or delegated to a mature specialist provider.

## Naming

Use stable vendor-neutral dotted identifiers.

Pattern:

```text
<surface>.<technology-or-interface>.<operation>
```

Examples:

```text
wireless.nfc.identify
wireless.subghz.observe
internal.uart.observe
internal.uart.autodetect
internal.spi.capture
internal.i2c.capture
debug.jtag.detect
debug.swd.detect
memory.acquire
firmware.extract
protocol.decode
```

Do not put a vendor/product name in the core capability identifier.

Bad:

```text
flipper.nfc.read
rp2040.spi.sniff
proxmark.hf.search
```

Those names belong in implementation/provider metadata.

## Capability descriptor

A capability descriptor defines semantics independent of implementation:

```text
capability_id
description
surface
operation
action_class
input_schema
output/evidence_schema
prerequisites
constraints
```

A descriptor should not need to know which board/tool will execute it.

## Capability implementation

A `CapabilityImplementation` is a concrete executable realization of a capability.

Conceptual fields:

```text
implementation_id
capability_id
provider_compatibility
implementation_kind
maturity
quality/fidelity metadata
toolchain constraints
artifact/source provenance
evidence schema
known limitations
verification references
```

Implementation kinds may include:

- built-in adapter operation;
- composed primitives;
- external specialist tool;
- generated host-side program;
- synthesized board firmware/app;
- generated decoder/debug automation artifact.

Examples:

```text
wireless.nfc.identify
  -> flipper.native.nfc-identify
  -> proxmark3.hf-identify

internal.uart.autodetect
  -> flipper.generated.uart-autodetect@<artifact-hash>
  -> rp2040.generated.pio-uart-autodetect@<artifact-hash>
```

## Hardware provider

A `HardwareProvider` is a controllable physical resource capable of executing or hosting implementations.

Examples:

- Flipper Zero;
- ESP32/RP2040/STM32 boards;
- Proxmark3;
- logic analyzer;
- OpenOCD-compatible debug probe;
- SDR;
- Linux SBC.

Providers should expose a normalized hardware descriptor rather than requiring the router to understand vendor command syntax.

See `PROGRAMMABLE_HARDWARE.md`.

## Maturity

Capability implementation maturity uses:

- `declared`;
- `simulated`;
- `implemented`;
- `hardware_verified`;
- `assessment_verified`.

For synthesized code, successful generation/build is still only implementation state. It is not hardware verification.

## Quality metadata

Different implementations of the same capability can have different quality.

Metadata may include:

- sampling/timing fidelity;
- receive/transmit behavior;
- confidence;
- supported protocols/rates;
- maximum duration/data size;
- electrical limits;
- setup cost;
- evidence detail;
- known limitations.

This lets the resolver choose an RP2040 PIO implementation over Flipper for a high-fidelity timing problem, or a specialist logic analyzer over both when a verified route already exists.

## Capability request

A request should describe the required capability and constraints without prematurely selecting a provider.

Conceptual shape:

```text
capability_id
target_id
target_component_id
test_case_id
required_constraints
normalized_inputs
preferred_provider (optional/advisory)
```

## Resolution order

The runtime should resolve a capability need in this order:

1. verified existing implementation;
2. composition of verified primitives;
3. mature specialist implementation/provider;
4. generated host-side implementation;
5. synthesized hardware implementation;
6. return a hardware/provider requirement if none can satisfy the physical constraints.

This order is deliberate. Dynamic synthesis is powerful but should not replace reliable existing tooling unnecessarily.

## Composition

Some capabilities can be constructed from lower-level primitives.

Example:

```text
internal.uart.autodetect
  <- gpio.edge_timing.observe
  + uart.receive
  + host.decode.score
```

If those primitives produce the required fidelity/evidence, the runtime can compose them instead of compiling new firmware.

Composition provenance should be stored just like a generated implementation.

## Synthesis request relationship

When no suitable implementation exists, the runtime can create a hardware-neutral `CapabilitySynthesisRequest` describing:

- objective;
- required physical interfaces;
- timing/bandwidth constraints;
- operation/action class;
- runtime bounds;
- expected evidence schema;
- candidate provider constraints.

The synthesis resolver then selects a compatible backend/provider.

See `CAPABILITY_SYNTHESIS.md`.

## Action model

Once a capability implementation is selected, it resolves into a typed Action.

Example:

```json
{
  "action_id": "act-001",
  "capability_id": "internal.uart.autodetect",
  "target_id": "camera-a",
  "action_class": "OBSERVE",
  "inputs": {
    "duration_seconds": 15
  }
}
```

The runtime should also know which `implementation_id` and provider will service the Action, even if those fields are stored in routing/execution metadata rather than the Action itself.

## Result model

Execution returns normalized evidence independent of the implementation mechanism.

```json
{
  "status": "success",
  "provider_id": "flipper-...",
  "capability_id": "internal.uart.autodetect",
  "implementation_id": "flipper.generated.uart-autodetect@...",
  "raw": {},
  "normalized": {},
  "limitations": []
}
```

The implementation returns evidence. It does not decide whether the evidence proves a vulnerability.

## Initial capability groups

### Wireless

```text
wireless.nfc.identify
wireless.nfc.observe
wireless.rfid.identify
wireless.subghz.observe
wireless.wifi.environment.scan
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
internal.uart.autodetect
internal.spi.capture
internal.i2c.capture
```

### Debug

```text
debug.jtag.detect
debug.swd.detect
debug.session.open
```

### Memory / firmware

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

The list is a design seed. Add semantics only when a real assessment use case requires them.

## Capability registration

Today adapters register executable capabilities after probing hardware and resolving verification state.

The generalized model should evolve toward registering **implementations** and provider resources separately:

```text
provider discovery
  -> HardwareDescriptor
  -> built-in implementations
  -> reusable synthesized implementations compatible with descriptor
  -> currently usable routes
```

Do not advertise a theoretical route that the connected hardware/toolchain/runtime cannot execute.

## Executable capability memory

A successful synthesized implementation should be rediscoverable in future sessions.

Persist:

- implementation ID;
- capability ID;
- source/artifact hash;
- compatible hardware descriptor constraints;
- toolchain version constraints;
- evidence schema;
- known limitations;
- HIL verification;
- assessment history.

This is the system's durable learning mechanism.

## Target relationship

TestCases still request capabilities rather than providers.

Example:

```text
Target component: camera debug header
TestCase: characterize suspected UART
Required capability: internal.uart.autodetect
```

The target may be a camera, drone, router, board or other embedded system. The same capability semantics can apply across them.

## Provider selection example

Available providers:

```text
Flipper Zero
  UART RX
  generated FAP backend

RP2040
  UART + PIO
  Pico SDK backend

Logic analyzer
  verified digital capture route
```

Request:

```text
internal.uart.autodetect
```

The resolver should prefer a verified existing route that meets fidelity constraints. If no route exists, it may synthesize for the best compatible provider.

The TestCase does not change.

## Versioning

Capability semantics should remain stable.

Implementation versions/artifact hashes may evolve independently. If capability semantics change incompatibly, create a versioned schema/new identifier rather than silently changing meaning.

## Acceptance

The generalized capability model is proven when:

- simulator and current Flipper implementations continue to use the same semantics;
- the planner contains no provider command syntax;
- unavailable routes cannot be planned as executable;
- implementation quality/compatibility drives routing;
- a missing capability can be synthesized and returned through the same evidence contract;
- a second provider can satisfy an overlapping capability without changing the TestCase;
- a verified generated implementation can be reused in a later assessment.
