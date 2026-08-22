# Roadmap

## Direction

Build the hardware execution layer independently first.

Prove the architecture with Flipper Zero.

Then add a second instrument to prove that the capability model is vendor-neutral.

Integrate with Null-AI after the runtime is stable.

## Milestone 0 — Foundation

Goal: make architecture executable before real hardware work expands.

Deliverables:

- domain models for engagement, target, instrument, capability, action, evidence, observation, and finding;
- capability registry;
- policy decision model;
- adapter protocol;
- deterministic simulator;
- JSON/YAML engagement schema;
- local evidence store;
- unit tests for routing and policy.

Acceptance:

- the simulator can complete one synthetic assessment;
- denied actions fail below the agent layer;
- assessment code contains no Flipper command strings.

## Milestone 1 — Flipper USB control

Goal: establish reliable communication with a stock supported Flipper Zero.

Deliverables:

- USB discovery;
- device identity and health;
- transport abstraction;
- structured RPC support where practical;
- typed CLI fallback where required;
- normalized errors and timeouts;
- Flipper capability registration.

Acceptance:

- connect/disconnect/reconnect is deterministic;
- failed device calls do not crash the runtime;
- no unrestricted command passthrough is exposed through the normal API.

## Milestone 2 — Flipper passive capability slice

Goal: prove at least four physical capability families.

Candidate capabilities:

- NFC identify/observe;
- LF RFID identify/observe;
- Sub-GHz observe;
- infrared observe;
- GPIO/UART inspection where safe and available.

Deliverables:

- typed Flipper actions;
- raw evidence capture;
- normalized observations;
- real-hardware verification fixtures/tests.

Acceptance:

- at least four capability families reach `hardware_verified`;
- each produces reproducible structured evidence.

## Milestone 3 — Assessment engine

Goal: run a real multi-step hardware assessment instead of isolated commands.

Deliverables:

- target model;
- test-case catalog;
- passive-first planner;
- persisted assessment state;
- step execution loop;
- human-action pause/resume state;
- inconclusive result handling.

Acceptance:

- one lab-owned target completes an end-to-end assessment;
- unavailable capabilities are not planned as executable;
- interrupted assessments can resume from persisted state.

## Milestone 4 — Policy and evidence hardening

Goal: prove that agent behavior is constrained independently of the model.

Deliverables:

- engagement manifest validation;
- target scope enforcement;
- action-class limits;
- allow/deny capability rules;
- approval records;
- evidence hashing/provenance;
- report finding/evidence linkage;
- hostile-output handling tests.

Acceptance:

- policy bypass attempts fail;
- deny precedence is tested;
- evidence is traceable to exact actions and instruments;
- findings cannot be emitted without evidence references.

## Milestone 5 — MCP and external agent interface

Goal: expose the assessment runtime to Claude, Codex, ChatGPT-compatible environments, and other MCP clients without exposing raw device control.

Deliverables:

- MCP server;
- high-level assessment tools;
- capability/status tools;
- policy-aware execution tools;
- local authentication/transport design as required by deployment mode.

Acceptance:

- an external agent can discover the Flipper, plan an assessment, execute allowed steps, and retrieve the report;
- the MCP layer cannot bypass the core policy engine.

## Milestone 6 — Flipper v0.1 release

Goal: publish the first useful, defensible project milestone.

Release criteria are defined in `MVP.md`.

The release demo must show:

- real Flipper discovery;
- several capability families;
- scoped assessment planning;
- a deterministic blocked action;
- evidence capture;
- an OWASP-ISTG-aligned report.

## Milestone 7 — Proxmark3 adapter

Goal: prove that the architecture is not a renamed Flipper wrapper.

Deliverables:

- Proxmark3 discovery and health;
- normalized overlapping NFC/RFID capabilities;
- capability quality metadata;
- deterministic routing between Flipper and Proxmark3;
- escalation from broad observation to deeper specialist analysis where an authorized test requires it.

Acceptance:

- the same test case can route to either instrument;
- no planner changes are needed to add Proxmark3;
- routing rationale is recorded.

## Milestone 8 — Internal bus and debug tooling

Goal: cover common wired embedded assessment surfaces.

Candidate adapters:

- sigrok-compatible logic analyzers;
- Saleae Logic automation;
- Bus Pirate-class tools;
- OpenOCD-compatible JTAG/SWD probes.

Capability areas:

- UART;
- SPI;
- I2C;
- JTAG;
- SWD;
- protocol decoding.

Acceptance:

- human probe/setup tasks are represented explicitly;
- electrical/physical prerequisites are validated or require operator confirmation.

## Milestone 9 — RF tooling

Goal: add a specialist RF instrument without weakening the safety model.

Candidate adapter:

- HackRF-class software-defined radio.

Initial focus:

- receive/capture;
- characterization;
- evidence integration.

Transmission remains separately gated.

## Milestone 10 — Firmware workflow

Goal: connect physical acquisition to firmware analysis.

Candidate integrations:

- firmware extraction adapters;
- Binwalk-compatible extraction;
- EMBA;
- FACT;
- selected emulation/rehosting tools.

Flow:

```text
physical evidence
  -> firmware artifact
  -> hash/provenance
  -> static analysis
  -> optional emulation
  -> correlated observations/findings
```

Do not reimplement mature firmware-analysis platforms inside this repo.

## Milestone 11 — Multi-instrument IoT hardware assessment

Goal: perform one assessment that uses several instruments under one target and evidence model.

Example:

```text
Flipper -> broad wireless discovery
Proxmark3 -> deeper RFID/NFC analysis
logic analyzer -> UART/SPI evidence
OpenOCD probe -> authorized debug-interface checks
firmware analyzer -> artifact analysis
```

Acceptance:

- one assessment graph spans multiple instruments;
- evidence remains traceable across tool transitions;
- routing decisions are reproducible.

## Milestone 12 — Null-AI integration

Goal: make this runtime the hardware/embedded execution layer of the Null-AI pentester.

Null-AI should be able to decompose a larger IoT product assessment into areas such as:

- hardware and physical interfaces;
- firmware;
- wireless;
- network services;
- web/API;
- mobile application;
- cloud backend.

Hardware Pentest Agent owns the physical/embedded execution portion.

## Post-1.0 research directions

Possible extensions:

- vision-assisted PCB component and test-point identification;
- richer target/component graphs;
- ChipWhisperer-class side-channel and fault-injection adapters under specialized policy;
- remote lab orchestration;
- reproducible test fixtures and digital twins;
- standards/compliance mappings beyond OWASP ISTG;
- automated remediation validation;
- hardware-security benchmark environments for agent evaluation.

## Release discipline

Do not advertise a planned capability as implemented.

Use these labels in documentation:

- planned;
- simulated;
- implemented;
- hardware verified;
- assessment verified.

Every release claim should be backed by a reproducible test or artifact in the repository.
