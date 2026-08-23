# Agent Capability Synthesis

## Goal

The hardware pentest agent should behave like an experienced hardware pentester, not a fixed command router.

When an assessment requires a physical capability that is not already available, the runtime should be able to create a new **capability implementation** for a compatible hardware provider.

Flipper FAP generation is the first synthesis backend, not the final abstraction.

```text
assessment objective
      |
      v
required physical capability
      |
      +--> verified implementation exists -> execute
      |
      +--> verified primitives compose it -> compose
      |
      +--> mature specialist tool exists -> route
      |
      +--> implementation missing
                 |
                 v
      CapabilitySynthesisRequest
                 |
          hardware resolver
                 |
      +----------+----------+-----------+
      |          |          |           |
   Flipper     ESP32      RP2040      other
    FAP       ESP-IDF     Pico SDK    backend
      |          |          |           |
      +----------+----------+-----------+
                 |
        build / provenance
                 |
          deploy / execute
                 |
              evidence
                 |
            HIL verify
                 |
       reusable implementation
```

## Generalized synthesis intent

`CapabilitySynthesisRequest` should describe the physical need before choosing a device/toolchain.

The target model should include fields such as:

- objective;
- required physical interfaces;
- timing/bandwidth requirements;
- read/interact/transmit/modify requirements;
- runtime bound;
- expected evidence schema;
- target/component context;
- electrical/physical constraints;
- candidate provider requirements.

Example:

```yaml
objective: detect likely UART configuration
required_interfaces:
  - uart_rx
  - gpio_timing
mode: observe
max_runtime_seconds: 20
evidence:
  baud_candidates: array
  decoded_samples: array
```

Only after this intent is defined should the resolver select Flipper, RP2040, ESP32 or another provider.

## Resolution before generation

Generation is a fallback, not the first response.

Resolution order:

1. reuse an existing verified implementation;
2. compose verified primitives;
3. use a mature external specialist tool;
4. generate bounded host-side software;
5. synthesize board-specific firmware/app;
6. request different hardware if available providers cannot satisfy the requirement.

This avoids unnecessary firmware creation and keeps results more reproducible.

## Common synthesis contracts

The long-term architecture should separate:

### `CapabilitySynthesisBackend`

Translates a hardware-neutral synthesis request into provider-specific source/project material.

### `BuildProvider`

Builds one reviewed immutable project and records toolchain/provenance information.

### `DeploymentProvider`

Transfers/activates the artifact on a specific provider and handles cleanup/recovery.

### `EvidenceChannel`

Returns bounded structured output from the generated implementation into the normal assessment evidence model.

### `CapabilityImplementationRecord`

Persists compatibility, source/artifact hashes, toolchain constraints, evidence schema, limitations and HIL verification.

## Candidate backends

The roadmap expects several backend families:

```text
Flipper       -> FAP / uFBT
ESP32         -> ESP-IDF / PlatformIO
RP2040        -> Pico SDK / PIO
STM32         -> STM32 HAL / Zephyr as appropriate
Linux SBC     -> bounded native/container tool
sigrok        -> generated decoder/analysis helper
OpenOCD/GDB   -> bounded debug automation artifact
```

A capability is not tied to one backend. The hardware resolver should select the implementation with the best fit for physical fidelity, timing, available interfaces and evidence needs.

---

# Flipper synthesis backend — current implementation

## Why FAPs

Flipper Zero supports external applications packaged as FAP files. Generated tools use ordinary external-app projects with an `application.fam` and target `f7`. The current build backend is uFBT.

Generated tools use the reserved `hpa_gen_` app-id namespace and `NullSquare` FAP category. They cannot overwrite catalogued applications.

## Current Flipper source policy

The first synthesis profile permits bounded `OBSERVE` and `INTERACT` helpers using declared interfaces such as:

- GPIO;
- UART;
- I2C;
- SPI;
- read-only storage access;
- infrared receive.

The policy rejects undeclared hardware-interface use and blocks APIs/behaviors that should enter through explicitly modeled capabilities, including RF/IR transmission, USB HID/BadUSB behavior, NFC emulation, arbitrary storage writes, destructive storage operations, device power/reset and inline assembly.

Generated source returns structured evidence through the injected `hpa_write_evidence_json()` helper. Agent-written code cannot choose an arbitrary result path. The trusted helper limits output to 4096 bytes and writes only the app-private result file.

Static analysis is not proof that generated code is safe or correct. It is one validation layer before build/deployment/HIL.

## Current Flipper build provenance

For every accepted generated project, the runtime records SHA-256 hashes for:

- agent-generated source;
- complete source tree including trusted support code;
- `application.fam`;
- synthesis manifest;
- build log;
- compiled FAP.

The builder re-hashes the reviewed project before invoking uFBT. Modification after review fails closed.

The subprocess contract is deliberately narrow:

- fixed executable (`ufbt` by default);
- no user-controlled shell command;
- `shell=False`;
- project root as working directory;
- bounded timeout;
- reduced child environment;
- one expected FAP artifact.

## Current generated FAP runtime

`GeneratedFlipperAdapter` exposes one synthesized capability at `IMPLEMENTED` maturity. Compilation does not make it `hardware_verified`.

The current runtime:

1. re-verifies local source/build provenance;
2. re-probes the expected Flipper identity and firmware state;
3. refuses to interrupt another running Flipper app;
4. transfers only reserved generated-app paths;
5. verifies the transferred artifact;
6. clears stale private result state;
7. launches the exact generated FAP;
8. enforces a runtime bound;
9. retrieves the bounded result artifact;
10. validates the result schema;
11. links execution evidence to build/source hashes;
12. cleans up ephemeral artifacts when configured.

The result schema is intentionally small:

```json
{
  "schema_version": "1",
  "status": "success",
  "observations": {}
}
```

`status` may be `success`, `inconclusive`, or `failed`.

---

## Required generalization work

The current implementation proves that generated hardware tooling can fit the normal runtime. It still needs to be lifted out of Flipper-specific assumptions.

Next work:

1. introduce `HardwareDescriptor` / provider contracts;
2. define the generalized synthesis request described above;
3. split common synthesis metadata from Flipper-specific FAP manifest/source rules;
4. define `BuildProvider`, `DeploymentProvider` and `EvidenceChannel` protocols;
5. refactor the current FAP pipeline behind `FlipperSynthesisBackend`;
6. persist immutable capability implementation records;
7. integrate synthesis into assessment planning when no suitable route exists;
8. add HIL promotion for synthesized implementations;
9. add a second materially different synthesis backend;
10. compare multiple provider implementations for the same capability need.

## Capability-gap assessment state

The assessment planner should eventually represent a missing-but-synthesizable route explicitly:

```text
READY
BLOCKED
SYNTHESIS_REQUIRED
```

A `SYNTHESIS_REQUIRED` step should carry the security objective and physical requirements, not generated source. Once a validated implementation exists, the step can be re-planned through the normal capability registry.

## Executable capability memory

A successful generated implementation should become reusable only after physical validation.

Lifecycle:

```text
generated
  -> IMPLEMENTED
  -> known physical fixture
  -> HIL verification
  -> HARDWARE_VERIFIED
  -> reusable registry implementation
```

Persist:

- capability ID;
- synthesis intent;
- compatible hardware descriptors;
- source/artifact hashes;
- toolchain versions;
- build/deployment provenance;
- evidence schema;
- known limitations;
- verification records;
- assessment usage history.

This is the mechanism by which the agent's hardware competence grows over time.

## Example: provider choice

Need:

```text
internal.spi.capture
```

Available hardware:

```text
Flipper: SPI-capable, moderate timing fidelity
RP2040: PIO available, high deterministic sampling fit
logic analyzer: verified sigrok adapter
```

The resolver may choose the logic analyzer if a verified capture route already exists. If it does not, it may synthesize an RP2040 PIO capture helper instead of forcing the task onto Flipper.

## Product principle

The product is not “full Flipper access,” “full Marauder access,” or “arbitrary firmware generation.”

It is:

> **A hardware pentester that can understand available physical resources and create a reproducible new implementation when the assessment requires a capability that does not yet exist.**
