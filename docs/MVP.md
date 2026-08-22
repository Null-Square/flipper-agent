# Flipper-First MVP

## Decision

The first MVP proves the agent-to-physical-instrument loop with a USB-connected Flipper Zero.

The MVP is passive-first and non-destructive.

It does not attempt to cover all IoT pentesting.

## Problem

Flipper Zero exposes several hardware security capabilities, but current integrations usually present device commands directly to a user or agent.

That does not solve the larger problem of safe, reproducible hardware assessment.

The MVP must prove that an assessment engine can use one physical instrument through a vendor-neutral capability model while preserving scope, policy, evidence, and assessment state.

## User

Primary users:

- authorized hardware and IoT pentesters;
- security researchers working in controlled labs;
- NullSquare engineers developing the future hardware execution layer for Null-AI.

## MVP outcome

Given an authorized target definition and a USB-connected Flipper Zero, the system must:

1. detect the Flipper;
2. identify the device and transport state;
3. register only hardware-verified capabilities;
4. load an engagement scope;
5. create or update a target model;
6. generate a passive-first assessment plan;
7. execute allowed bounded steps;
8. pause for required physical setup or approval;
9. block disallowed steps below the LLM layer;
10. preserve evidence and execution metadata;
11. produce observations and an assessment report;
12. mark unsupported or ambiguous results as inconclusive.

## Required vertical slice

The MVP must implement one complete path:

```text
Engagement
  -> Target
  -> Flipper discovery
  -> Capability registry
  -> Test selection
  -> Plan
  -> Policy check
  -> Execution
  -> Evidence
  -> Observation
  -> Report
```

A feature is not complete if it exists only as an isolated Flipper command.

## Supported transport

### Required

- USB connection to Flipper Zero.

### Deferred

- Bluetooth Low Energy (BLE);
- Wi-Fi Dev Board transport;
- remote relays.

The transport interface must remain replaceable.

## Required capability families

The initial v0.1 Flipper implementation targets four distinct hardware families:

- `infrared.observe`;
- `wireless.subghz.observe`;
- `wireless.nfc.identify`;
- `internal.gpio.inspect`.

These four exercise different physical semantics: passive optical reception, passive RF reception, non-destructive NFC interaction, and human-prepared wired input inspection.

Future Flipper families can include LF RFID and UART only after their data-handling and physical-safety contracts are modeled explicitly.

Do not claim a capability until the adapter proves it on real hardware and the verification record remains valid for the current instrument, firmware, and adapter version.

## Capability maturity states

Each capability has one state:

- `declared` - modeled but not implemented;
- `simulated` - deterministic simulator works;
- `implemented` - adapter path exists;
- `hardware_verified` - validated on real hardware;
- `assessment_verified` - used successfully in an end-to-end test case.

Only `hardware_verified` and `assessment_verified` capabilities may be presented as working in release documentation.

## Test cases

The first test catalog should be small.

Each test case must declare:

- target component;
- purpose;
- prerequisites;
- required capability;
- action class;
- expected evidence;
- stop conditions;
- result rules;
- optional OWASP ISTG mapping.

### Observe infrared activity

Goal: record decoded or raw infrared observations from a lab-owned source.

Default action class: `OBSERVE`.

The capability never transmits or replays an infrared signal.

### Observe Sub-GHz activity

Goal: record scoped, receive-only observations at an approved frequency.

Default action class: `OBSERVE`.

The MVP does not replay, jam, brute-force, or transmit captured signals.

### Identify an NFC interface

Goal: determine whether an authorized target presents a detectable NFC protocol family and record only the protocol hierarchy needed for identification.

Default action class: `INTERACT`.

The reader must energize/query a tag to identify its protocol, so this is deliberately not mislabeled as passive observation. The MVP does not extract application data, write, clone, emulate, or attack keys.

### Inspect a prepared GPIO input

Goal: read one digital level from a supported non-debug external header pin after operator safety checks.

Default action class: `OBSERVE` with `requires_human_action=true`.

The operator must configure the chosen pin as input before connecting the target, confirm common ground, and confirm the signal voltage is safe. The assessment action itself invokes only `gpio read <PIN>` and never changes GPIO mode or drives an output.

## Engagement manifest

The MVP must load a machine-readable engagement manifest.

Example shape:

```yaml
engagement_id: lab-smart-lock-001
valid_from: 2026-08-22T00:00:00Z
valid_until: 2026-08-23T00:00:00Z
mode: non-destructive
max_action_class: INTERACT
targets:
  - target_id: smart-lock-a
    description: Lab-owned smart lock
allowed_capabilities:
  - infrared.observe
  - wireless.subghz.observe
  - wireless.nfc.identify
  - internal.gpio.inspect
denied_capabilities:
  - "*.transmit"
  - "*.emulate"
  - "*.write"
```

The schema must reject invalid values.

## Policy requirements

The MVP must enforce policy deterministically.

The policy engine must check:

- engagement is active;
- target is in scope;
- capability is allowed;
- action class does not exceed the engagement limit;
- required physical constraints are satisfied;
- required human action is complete;
- required approval exists;
- required instrument capability is available and hardware-verified.

The policy result must be one of:

- `ALLOW`;
- `REQUIRE_APPROVAL`;
- `REQUIRE_HUMAN_ACTION`;
- `DENY`.

The LLM cannot override `DENY` or manufacture a hardware-verification result.

## Evidence requirements

Every executed step must create an execution record.

Minimum fields:

```text
execution_id
engagement_id
target_id
test_case_id
capability_id
action_id
action_class
instrument_id
adapter_name
adapter_version
started_at
finished_at
normalized_inputs
result_status
raw_artifact_reference
raw_artifact_hash
normalized_observation
limitations
```

If an operation has no external artifact, preserve the raw response or canonical serialized result.

Hardware-verification evidence is separate from assessment evidence. Capability discovery must resolve the verification store before a physical operation becomes available to the agent.

## Report requirements

The MVP report must contain:

- engagement summary;
- target summary;
- instruments used;
- tests planned;
- tests executed;
- blocked/skipped/inconclusive tests;
- evidence references;
- observations;
- confirmed findings, if any;
- limitations;
- OWASP ISTG mappings where applicable.

The report must not invent vulnerabilities from unconfirmed observations.

## Simulator requirement

Build a deterministic simulator before depending on physical hardware for every test.

The simulator must support:

- instrument discovery;
- configurable capabilities;
- successful actions;
- blocked actions;
- timeouts;
- malformed results;
- unavailable capabilities;
- human-action requirements.

The same runtime tests must work with the simulator and Flipper adapter.

## MCP scope

MCP is optional for the earliest vertical slice but required before v0.1 release.

The first MCP server must expose assessment-level tools.

It must not expose unrestricted serial CLI passthrough.

## Explicit non-goals

The v0.1 MVP does not include:

- destructive testing;
- jamming;
- unrestricted RF transmission;
- brute-force credential attacks;
- arbitrary NFC/RFID cloning;
- autonomous device/tag emulation;
- arbitrary BadUSB payload execution;
- arbitrary shell access;
- arbitrary FAP execution;
- GPIO output driving during an assessment action;
- fault injection;
- chip-off or invasive flash extraction;
- firmware reverse engineering;
- cloud/API/mobile assessment;
- multi-instrument routing;
- unattended remote physical testing.

## Acceptance criteria

The MVP is complete only when all conditions are true:

- [ ] A stock supported Flipper Zero connects over USB.
- [ ] Device identity and health are discovered automatically.
- [ ] The capability registry reports only capabilities backed by valid verification evidence.
- [ ] `infrared.observe` is hardware-verified.
- [ ] `wireless.subghz.observe` is hardware-verified.
- [ ] `wireless.nfc.identify` is hardware-verified.
- [ ] `internal.gpio.inspect` is hardware-verified.
- [ ] An engagement manifest loads and validates.
- [ ] An out-of-scope action is denied without LLM cooperation.
- [ ] A planner cannot route to an unavailable capability.
- [ ] A human-required step pauses execution cleanly.
- [ ] A multi-step assessment completes against a lab-owned target.
- [ ] Each executed step produces structured evidence.
- [ ] Raw artifacts or raw responses are preserved and hashed when applicable.
- [ ] Inconclusive results remain inconclusive.
- [ ] The report references actual evidence identifiers.
- [ ] Relevant tests map to OWASP ISTG identifiers or sections.
- [ ] The same assessment engine runs against the simulator unchanged.
- [ ] No assessment code depends on Flipper-specific command strings.

## Demo definition

A release demo should use a lab-owned target with at least two relevant interfaces.

The operator runs one command or agent request. The system:

1. loads the engagement;
2. detects the Flipper;
3. resolves verified capabilities;
4. proposes the assessment plan;
5. executes allowed bounded steps;
6. pauses for any required human step;
7. stores evidence;
8. generates a report.

The demo should make the architecture visible. It should not rely on a flashy exploit to prove value.
