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
3. register supported capabilities;
4. load an engagement scope;
5. create or update a target model;
6. generate a passive-first assessment plan;
7. execute allowed observation steps;
8. block disallowed steps below the LLM layer;
9. preserve evidence and execution metadata;
10. produce observations and an assessment report;
11. mark unsupported or ambiguous results as inconclusive.

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

The MVP must demonstrate at least four distinct families where the stock device, firmware, and selected control surface make the operation reliable.

Candidate families:

- `wireless.nfc.identify`;
- `wireless.nfc.observe`;
- `wireless.rfid.identify`;
- `wireless.subghz.observe`;
- `infrared.observe`;
- `internal.gpio.inspect`;
- `internal.uart.observe`.

Do not claim a capability until the adapter proves it on real hardware.

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

Initial examples can include:

### Identify an NFC interface

Goal: determine whether an authorized target presents a detectable NFC technology and record the observation.

Default action class: `OBSERVE`.

Output: technology/protocol metadata supported by the instrument plus raw evidence.

### Identify an LF RFID interface

Goal: determine whether an authorized target presents a detectable low-frequency RFID technology.

Default action class: `OBSERVE`.

### Observe Sub-GHz activity

Goal: record scoped, passive observations in an approved frequency context.

Default action class: `OBSERVE`.

The MVP does not replay, jam, brute-force, or transmit captured signals.

### Inspect an approved wired/debug interface

Goal: capture read-only observations from a physically connected interface after required safety checks.

Default action class: `OBSERVE` or `INTERACT` depending on the operation.

Human confirmation is required when physical setup or voltage validation cannot be determined automatically.

## Engagement manifest

The MVP must load a machine-readable engagement manifest.

Example shape:

```yaml
engagement_id: lab-smart-lock-001
valid_from: 2026-08-22T00:00:00Z
valid_until: 2026-08-23T00:00:00Z
mode: non-destructive
max_action_class: OBSERVE
targets:
  - target_id: smart-lock-a
    description: Lab-owned smart lock
allowed_capabilities:
  - wireless.nfc.*
  - wireless.rfid.*
  - wireless.subghz.observe
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
- required approval exists;
- required instrument capability is available.

The policy result must be one of:

- `ALLOW`;
- `REQUIRE_APPROVAL`;
- `REQUIRE_HUMAN_ACTION`;
- `DENY`.

The LLM cannot override `DENY`.

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
- [ ] The capability registry reports only capabilities the adapter can prove.
- [ ] At least four capability families are hardware-verified.
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

A release demo should use a lab-owned target with at least two observable interfaces.

The operator runs one command or agent request. The system:

1. loads the engagement;
2. detects the Flipper;
3. shows available capabilities;
4. proposes the assessment plan;
5. executes allowed passive steps;
6. pauses for any required human step;
7. stores evidence;
8. generates a report.

The demo should make the architecture visible. It should not rely on a flashy exploit to prove value.
