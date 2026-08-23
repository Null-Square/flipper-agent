# Hardware Descriptors and Providers

## Purpose

A hardware provider describes **physical resources that can be used to implement security-testing capabilities**. It is deliberately different from an instrument adapter's current capability list.

A Flipper Zero may physically expose UART, SPI, I2C, GPIO, NFC, Sub-GHz and infrared resources even when the current adapter has no verified implementation for a requested test. That difference is what allows the synthesis layer to reason about whether a missing capability could be built for the connected hardware.

```text
security capability need
       |
       v
existing implementation? ---- yes ---> normal adapter execution
       |
       no
       v
HardwareRequirement
       |
       v
HardwareProviderRegistry
       |
       v
HardwareDescriptor compatibility
       |
       v
future CapabilitySynthesisBackend
```

## Core objects

### `HardwareIdentity`

Normalized identity for one connected provider instance:

- provider ID;
- hardware kind/model;
- active transport;
- firmware version where known;
- provider/adapter version where known.

Provider IDs should be stable enough to bind descriptor and later implementation provenance to the connected device.

### `HardwareDescriptor`

Versioned immutable snapshot containing:

- architecture;
- physical interfaces/resources;
- artifact types the provider can consume;
- supported build/toolchain families;
- deployment/recovery methods;
- evidence channels;
- relevant limits;
- verified limitations.

The descriptor has a canonical SHA-256 `fingerprint`. Later capability-implementation records can bind to this fingerprint so the runtime knows which physical description was used when selecting/building an implementation.

### `HardwareInterface`

One physical resource, such as:

- GPIO;
- UART;
- SPI;
- I2C;
- NFC;
- Sub-GHz radio;
- infrared;
- USB;
- storage.

Interface attributes are provider-specific facts. The core compatibility layer normally reasons over the stable `kind` first and may use attributes for richer constraints later.

### `HardwareRequirement`

Small vendor-neutral compatibility request used before implementation selection. The first version can require:

- interface kinds;
- acceptable artifact types;
- acceptable architectures.

This is intentionally smaller than the future `CapabilitySynthesisRequest`; it is the physical compatibility primitive that request will build upon.

### `HardwareProvider`

Structural contract:

```python
class HardwareProvider(Protocol):
    def probe_hardware(self) -> HardwareIdentity: ...
    def describe_hardware(self) -> HardwareDescriptor: ...
```

A provider may wrap an existing instrument adapter, vendor SDK, board manager, debug probe, or simulator. Provider discovery does not replace the existing `InstrumentAdapter` execution contract.

## Physical potential is not capability maturity

A descriptor states what resources the hardware offers. It does **not** state that every possible security test using those resources is implemented or verified.

For example:

```text
Flipper descriptor: UART exists

!=

Capability registry: internal.uart.autodetect is hardware_verified
```

The future synthesis resolver can use the first fact to decide that generating a UART helper is physically plausible. Only successful build/deployment/HIL evidence can create a reusable capability implementation.

## Provider registry

`HardwareProviderRegistry` stores validated provider descriptors and evaluates requirements without vendor-specific branches.

Registration fails if a provider's probed identity and descriptor identity differ. This prevents a descriptor snapshot from being silently attached to another connected device.

The registry exposes both:

- compatible routes only; and
- evaluation results including incompatibility reasons.

This will be reused by generalized synthesis in issue #39.

## Flipper provider

`FlipperHardwareProvider` is provider #1. It layers over the existing `FlipperAdapter` identity/transport and describes known Flipper Zero physical resources plus the current FAP build/deployment/evidence path.

The descriptor intentionally includes physical resources beyond today's fixed adapter handlers. That is the point of the provider abstraction.

Toolchain availability is currently represented as host-dependent rather than assumed installed. A later build-provider layer will detect and pin exact toolchain versions.

## Simulator provider

`SimulatedHardwareProvider` implements the same provider contract and exists so provider selection/compatibility can be tested without physical devices.

Simulator descriptors and transcript replay must never be treated as hardware-verification evidence.

## Next step

Issue #39 generalizes the existing generated-FAP pipeline behind:

- `CapabilitySynthesisBackend`;
- `BuildProvider`;
- `DeploymentProvider`;
- `EvidenceChannel`/implementation provenance;
- `CapabilityImplementationRecord`.

The generic synthesis request will use hardware requirements and descriptors before asking a model to write board-specific code.
