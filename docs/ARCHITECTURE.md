# Architecture

## Decision

Hardware Pentest Agent is a vendor-neutral execution runtime for authorized hardware and embedded security assessments.

The runtime must separate pentest intent from device-specific commands.

Flipper Zero is the first adapter. It must not define the core API.

## Goals

The architecture must support these behaviors:

- represent an engagement and target explicitly;
- select applicable hardware/embedded tests;
- discover connected instruments and their capabilities;
- route a capability request to an appropriate instrument;
- validate scope, action risk, and physical constraints before execution;
- pause for a human physical action or approval when required;
- retain raw evidence and normalized observations;
- promote only supported observations to findings;
- expose the runtime through Python, CLI, MCP, and later Null-AI integration;
- add a second instrument without changing assessment logic.

## Non-goals

The core runtime must not:

- reimplement specialist hardware tools when a stable automation surface exists;
- give an LLM arbitrary shell or serial access as the normal execution path;
- make MCP the internal architecture;
- encode Flipper-specific command names in assessment logic;
- infer authorization from a prompt;
- treat every anomaly as a vulnerability;
- assume physical setup is safe without validation.

## System layers

```text
+---------------------------------------------------------+
|                    Security Agent                       |
| planner / evaluator / future Null-AI integration        |
+---------------------------+-----------------------------+
                            |
                            v
+---------------------------------------------------------+
|                 Assessment Runtime                      |
| target model | test selection | state | jobs            |
+---------------------------+-----------------------------+
                            |
                            v
+---------------------------------------------------------+
|                 Capability Runtime                      |
| registry | discovery | routing | typed actions          |
+---------------------------+-----------------------------+
                            |
              +-------------+-------------+
              |                           |
              v                           v
+-------------------------+   +---------------------------+
| Policy & Constraints    |   | Evidence & Findings       |
| scope | risk | approval |   | artifacts | provenance    |
| physical limits         |   | observations | findings   |
+------------+------------+   +-------------+-------------+
             |                              ^
             +---------------+--------------+
                             |
                             v
+---------------------------------------------------------+
|                  Instrument Adapters                    |
| Flipper | Proxmark | sigrok | OpenOCD | HackRF | ...    |
+---------------------------------------------------------+
```

## Core domain objects

### Engagement

Defines the authorized assessment context.

Required fields include:

- `engagement_id`;
- target references;
- valid time window;
- allowed capability families;
- denied capability families;
- maximum action class;
- operator/approval requirements;
- notes about legal or environmental constraints.

An engagement record is a technical policy input. It is not proof of legal authorization.

### Target

Represents the device or system under test.

A target can include:

- manufacturer/model;
- hardware revision;
- firmware version;
- known interfaces;
- expected wireless technologies;
- physical access level;
- test notes;
- discovered components.

The target model should evolve as evidence is collected.

### Instrument

Represents a connected tool.

Examples:

- Flipper Zero;
- Proxmark3;
- Saleae-compatible logic analyzer;
- sigrok-supported device;
- OpenOCD-supported debug probe;
- HackRF-class SDR.

An instrument advertises capabilities. It does not define assessment intent.

### Capability

A stable, vendor-neutral operation that the runtime can request.

Examples:

- `wireless.nfc.identify`;
- `wireless.subghz.observe`;
- `internal.uart.observe`;
- `debug.jtag.detect`;
- `protocol.decode`.

See `CAPABILITY_MODEL.md`.

### TestCase

Represents the security question being tested.

A test case declares:

- purpose;
- target component;
- prerequisites;
- required capabilities;
- expected evidence;
- stop conditions;
- success/inconclusive/failure conditions;
- optional mappings to OWASP ISTG or other references.

### Action

A concrete execution request produced from a capability.

An action is typed and validated before it reaches an adapter.

### Evidence

Raw or normalized output produced by an action.

Evidence must preserve provenance.

### Observation

A statement directly supported by evidence.

Example:

> The target presented an ISO/IEC 14443-A compatible NFC interface during the observation window.

### Finding

A security conclusion supported by one or more observations.

A finding must state evidence, impact, limits, and remediation.

## Assessment state machine

```text
CREATED
  |
  v
MODELED
  |
  v
PLANNED
  |
  v
READY
  |
  +--> HUMAN_ACTION_REQUIRED
  |           |
  |           v
  |         READY
  |
  +--> APPROVAL_REQUIRED
  |           |
  |           v
  |         READY
  |
  v
RUNNING
  |
  +--> BLOCKED
  +--> INCONCLUSIVE
  +--> FAILED
  +--> COMPLETED
```

The runtime must persist state transitions. It must not rely on LLM conversation memory as the assessment record.

## Capability routing

The router receives a capability request and a target context.

It performs these steps:

1. Find connected instruments that advertise the capability.
2. Remove instruments that cannot satisfy required constraints.
3. Apply engagement policy.
4. Rank viable instruments.
5. Return the selected route and rationale.
6. Require approval if policy requires it.
7. Execute through the selected adapter.

Initial routing can use deterministic priorities. Later versions can use richer cost, confidence, fidelity, and risk scores.

## Adapter contract

Every instrument adapter must implement a small stable contract:

```python
class InstrumentAdapter(Protocol):
    def probe(self) -> InstrumentIdentity: ...
    def capabilities(self) -> list[CapabilityDescriptor]: ...
    def validate(self, action: Action) -> ValidationResult: ...
    def execute(self, action: Action) -> ExecutionResult: ...
```

The adapter may internally use a CLI, RPC protocol, local API, daemon, or vendor SDK.

The core runtime must not depend on those details.

## Flipper adapter

The first Flipper transport is USB.

The adapter may use documented Flipper control surfaces such as the CLI and protobuf RPC. The implementation must prefer structured RPC where practical and use CLI only behind typed adapter operations.

The first adapter must support:

- device discovery and identity;
- capability registration;
- connection health;
- normalized execution results;
- timeout/cancellation behavior;
- deterministic error mapping;
- evidence collection;
- safe recovery after failed actions.

## Human action model

Some hardware steps need physical work.

Represent them explicitly:

```text
HumanAction
- instruction
- reason
- required confirmation
- safety checks
- expected resulting state
```

The runtime must stop until the operator confirms the required state.

Examples include probe placement, voltage measurement, enclosure access, and target power cycling.

## Evidence architecture

Each execution event must link:

```text
Engagement
  -> Target
  -> TestCase
  -> Capability
  -> Action
  -> Instrument
  -> Adapter version
  -> Raw artifact/output
  -> Observation
```

Artifacts should be content-addressed or hashed when practical.

The first implementation can use local files plus JSON metadata. Storage must remain replaceable so Null-AI can later use its own evidence store.

## Agent boundary

The agent may:

- build a target model from confirmed information;
- propose a test plan;
- choose among allowed test cases;
- interpret normalized observations;
- propose follow-up tests;
- draft findings.

The agent must not:

- bypass scope enforcement;
- send raw arbitrary commands to an instrument through the normal path;
- override physical constraints;
- silently approve actions that require an operator;
- promote unsupported hypotheses to confirmed findings.

## MCP boundary

MCP exposes the runtime to external agents.

The initial MCP surface should remain small:

- `hardware_status`;
- `hardware_instruments`;
- `hardware_capabilities`;
- `assessment_create`;
- `assessment_plan`;
- `assessment_next_step`;
- `assessment_execute_step`;
- `assessment_evidence`;
- `assessment_report`.

Raw Flipper command passthrough is not part of the normal MCP contract.

## Null-AI integration

Do not merge the repositories during the MVP.

The runtime must first prove:

1. a real Flipper assessment;
2. deterministic policy enforcement;
3. evidence provenance;
4. a second instrument using the same capability API.

After that, Null-AI can consume this runtime as a package, local service, MCP provider, or native tool provider.

## Definition of architectural success

The architecture is valid when the same test case can run against a simulator, Flipper adapter, or second suitable instrument without changing the assessment planner or domain model.
