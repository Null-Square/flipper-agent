# Flipper-First Reference MVP

## Purpose

The first MVP is a **reference-provider certification**, not the final product boundary.

It proves that Hardware Pentest Agent can connect an outer agent harness to real physical hardware through durable target state, capability routing, execution, evidence and hardware verification.

Flipper Zero is used first because it exposes several useful physical interfaces and supports external FAP applications. The broader programmable-hardware architecture is defined in `PROGRAMMABLE_HARDWARE.md`.

## What the MVP must prove

Given an authorized target definition and a connected Flipper Zero, with the Marauder board when Wi-Fi is needed, the runtime must:

1. discover and identify the physical stack;
2. expose only currently usable implementations;
3. load durable engagement scope;
4. create a deterministic assessment from versioned TestCases;
5. execute bounded steps through the normal policy/evidence runtime;
6. pause cleanly for operator physical actions or approvals;
7. preserve evidence and provenance;
8. recover/resume without relying on model conversation history;
9. support an external harness through Python/MCP/CLI;
10. prove selected capabilities on real hardware rather than mocks alone.

## Reference capability slice

The native Flipper reference set currently targets:

- `infrared.observe`;
- `wireless.subghz.observe`;
- `wireless.nfc.identify`;
- `internal.gpio.inspect`.

The Flipper + ESP32 Marauder composite adds a Wi-Fi reference slice including passive environment/frame observations and explicitly modeled approved network-discovery operations.

A capability is not considered working merely because its adapter code exists. Real release claims require appropriate hardware-verification records.

## Capability maturity

Use these states consistently:

- `declared` — modeled but not implemented;
- `simulated` — deterministic simulator works;
- `implemented` — an implementation path exists;
- `hardware_verified` — validated on real hardware under the verification contract;
- `assessment_verified` — used successfully inside an end-to-end assessment.

Generated artifacts have build/provenance state in addition to capability maturity. Compilation does not imply hardware verification.

## Assessment vertical slice

```text
Persisted Engagement
  -> Target
  -> Hardware discovery
  -> Capability implementations
  -> TestCase selection
  -> Deterministic plan
  -> Physical/policy gates
  -> Execution
  -> Evidence
  -> Observation
  -> Report
```

A feature is not complete if it exists only as an isolated Flipper command.

## Harness-neutral requirement

The MVP is now expected to work behind the framework-free service layer and MCP interface.

An external harness should be able to:

- list persisted engagements/assessments;
- obtain compact durable assessment context;
- obtain deterministic candidate tests and methodology semantics;
- create an assessment from persisted scope;
- execute at most one step at a time;
- observe when a local operator gate is required;
- resume later without depending on prior model conversation.

The outer harness does not define TestCases, capability action classes or hardware-verification state.

## Physical test cases

### Observe infrared activity

Bounded receive-only evidence from a lab-owned source.

### Observe approved Sub-GHz activity

Bounded receive-only evidence at an approved frequency.

### Identify an NFC interface

Bounded protocol-family identification. Because the reader energizes/queries a tag, this is modeled as `INTERACT` rather than falsely calling it passive.

### Inspect a prepared GPIO input

Read one supported prepared digital input after the operator completes required electrical setup.

### Marauder Wi-Fi reference tests

Use the composite provider to prove passive Wi-Fi observation, preflight, exact hardware identity, known-AP fixture verification and selected approved network-discovery behavior.

The Marauder CLI itself is not the capability model.

## Generated FAP reference backend

The MVP also includes the first capability-synthesis backend:

```text
CapabilitySynthesisRequest
  -> generated FAP project
  -> review/policy
  -> uFBT build
  -> immutable hashes
  -> bounded deployment
  -> structured result evidence
  -> cleanup
```

The current FAP pipeline proves the mechanics needed for later ESP32/RP2040/STM32 and other synthesis backends.

## MVP physical exit criteria

The reference MVP is physically credible only when the real bench verifies at least:

- [ ] Flipper discovery and stable identity;
- [ ] expected firmware/device state;
- [ ] valid hardware verification for the native reference capability families;
- [ ] composite Flipper + Marauder preflight where Wi-Fi is included;
- [ ] passive Wi-Fi fixture verification;
- [ ] approved network HIL when that profile is requested;
- [ ] generated-FAP build/deploy/execute/evidence/cleanup smoke test;
- [ ] sanitized real-device transcripts captured for replay CI;
- [ ] one persisted multi-step assessment completed against a lab-owned target;
- [ ] evidence integrity and report linkage verified;
- [ ] interrupted execution recovery demonstrated without blind automatic retry.

## Strategic exit criterion

The Flipper reference phase should not end with “we added many commands.”

The important transition into the next phase is a **capability-gap experiment**:

```text
assessment needs a physical capability
        |
no exact implementation exists
        |
resolver determines Flipper can host it
        |
agent synthesizes a bounded FAP
        |
build -> deploy -> execute -> evidence
        |
HIL verifies the implementation
        |
implementation is persisted for reuse
        |
assessment resumes
```

A suitable first scenario is UART autodetection/observation on an authorized unknown PCB because it exercises physical setup, timing, generated code, structured evidence and reusable capability memory without requiring a prebuilt fixed command for the exact task.

## What comes after this MVP

The next architecture phase is deliberately **not** “Flipper v0.2 with more buttons.”

It is:

1. normalized `HardwareDescriptor` contracts;
2. physical capability graph/resolution;
3. generalized synthesis/build/deployment protocols;
4. refactor FAP generation as `FlipperSynthesisBackend`;
5. persistent executable capability implementations;
6. a second materially different programmable provider;
7. real camera/drone/unknown-PCB target assessments spanning multiple providers.

See `ROADMAP.md`.

## Explicit non-goals of the reference MVP

The first certification does not claim:

- arbitrary support for any board without a provider/toolchain path;
- autonomous invasive/fault-injection testing;
- complete firmware reverse engineering;
- complete IoT product coverage;
- production-grade unattended remote labs;
- that generated code is physically correct merely because it compiled;
- that Flipper is always the best provider for a hardware task.

## Demo definition

A strong demo should make the architecture visible:

1. an outer harness connects through MCP or Python;
2. the runtime loads persisted authorized scope;
3. real Flipper/Marauder hardware is discovered and verified;
4. the agent receives deterministic methodology/candidate context;
5. bounded tests execute and produce evidence;
6. a physical/operator gate pauses correctly if encountered;
7. assessment state can be resumed from another session/harness;
8. ideally, one missing low-level capability is synthesized as a FAP and returned as normal evidence.

That final step is the bridge from **Flipper automation** to the intended **adaptive hardware pentester**.
