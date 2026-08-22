# Assessment Runtime

## Purpose

The assessment layer turns isolated instrument capabilities into a reproducible security assessment.

It is intentionally deterministic. An LLM may propose objectives or explain results, but it is not required to preserve assessment state, select unavailable hardware, bypass policy, or remember which physical step comes next.

## Runtime flow

```text
Engagement + Target
        |
        v
Versioned test catalog
        |
        v
Capability registry
        |
        v
AssessmentPlanner
        |
        +-- unavailable capability -> BLOCKED
        +-- policy deny -> BLOCKED
        +-- physical setup needed -> HUMAN_ACTION_REQUIRED
        +-- approval needed -> APPROVAL_REQUIRED
        +-- otherwise -> READY
        |
        v
Persisted AssessmentState
        |
        v
AssessmentRunner (one step at a time)
        |
        +-- persist before execution
        +-- deterministic policy re-check
        +-- instrument validation
        +-- typed adapter execution
        +-- evidence capture
        +-- persist result immediately
        |
        v
Observation
```

The same planner and runner can operate against the deterministic simulator or a verified physical adapter.

## Test catalog

The v0.1 catalog is deliberately small and tracks only the four current Flipper MVP capability families:

| Test case | Capability | Class | Special gate |
|---|---|---:|---|
| `flipper.ir.observe.v1` | `infrared.observe` | `OBSERVE` | none |
| `flipper.subghz.observe.v1` | `wireless.subghz.observe` | `OBSERVE` | none |
| `flipper.nfc.identify.v1` | `wireless.nfc.identify` | `INTERACT` | none |
| `flipper.gpio.inspect.v1` | `internal.gpio.inspect` | `OBSERVE` | human physical setup |

Each `TestCase` declares:

- purpose;
- prerequisites;
- required capability;
- action class;
- expected evidence;
- stop conditions;
- result rules;
- optional OWASP ISTG references;
- default and required inputs;
- human-action or approval requirements.

The catalog should not grow faster than hardware capability verification.

## Passive-first planning

Planning is deterministic and ordered by action class before test identifier. Lower-risk observation work therefore appears before bounded interactions such as NFC identification.

A test that requires a capability that is not currently advertised by the registry remains visible as a `BLOCKED` step with a reason, but has no `Action` and is never executable.

The planner also blocks a test if:

- the target is outside engagement scope;
- the available instrument advertises a different action class than the test requires;
- required test inputs are missing;
- the engagement denies the capability;
- the action exceeds the engagement maximum action class.

## Human and approval gates

`HUMAN_ACTION_REQUIRED` and `APPROVAL_REQUIRED` are persisted states, not chat prompts.

For a GPIO inspection, for example, the runner stops before execution if physical setup has not been confirmed. The stored state contains the exact gated step, so a new process can reload the assessment and resume after the operator performs the required work.

The runner can also handle sequential gates. If a future action requires both physical setup and explicit approval, human confirmation can be satisfied first and the same persisted step can then move to `APPROVAL_REQUIRED`.

## Crash-visible execution

Before calling an instrument, the runner persists the selected step as `RUNNING`.

This is deliberate. If the process, host, or hardware connection fails during an operation, the stored state does not falsely show the step as untouched. A later recovery workflow can inspect the `RUNNING` state and decide whether the step is safe to retry.

Automatic retry is not part of this first M3 slice.

## Evidence linkage

Every physically executed step must have an evidence ID before it can enter a terminal execution result such as:

- `SUCCESS`;
- `INCONCLUSIVE`;
- `FAILED`.

A policy denial or lost route that prevents execution may become `BLOCKED` without evidence because no instrument action occurred.

The runner creates an `Observation` only from an evidence-backed successful or inconclusive execution. The observation references the exact evidence ID.

An execution failure is recorded on the step and in evidence but is not automatically translated into a security observation.

## Observations, hypotheses, and findings

The model keeps these concepts separate:

```text
Evidence
  -> Observation
      -> optional Hypothesis
          -> optional Finding
```

The runtime never promotes a raw observation into a vulnerability finding automatically.

A `CONFIRMED` finding is structurally invalid unless it references at least one evidence ID.

This is intentionally stricter than a prose reporting workflow: the data model prevents a confirmed finding with no provenance.

## Inconclusive semantics

An inconclusive hardware result remains `INCONCLUSIVE` through assessment state.

Examples include:

- no IR signal observed during a bounded window;
- no decodable Sub-GHz packet;
- no NFC protocol identified.

The absence of an observation is not converted into a claim that the interface is secure or absent.

## Persistence

`LocalAssessmentStore` writes one versioned JSON document per assessment under:

```text
.hardware-pentest/assessments/
```

Writes are atomic within the local filesystem: state is written to a temporary file and then replaced into the canonical assessment path.

Assessment IDs are restricted to a safe filename character set. Path-like identifiers are rejected.

The stored state is sufficient to resume without relying on LLM conversation history.

## Simulator parity

The deterministic simulator now exposes the same four default capability families and action classes as the Flipper MVP:

- `infrared.observe` -> `OBSERVE`;
- `wireless.subghz.observe` -> `OBSERVE`;
- `wireless.nfc.identify` -> `INTERACT`;
- `internal.gpio.inspect` -> `OBSERVE`.

The previously simulated LF RFID default was removed because the physical Flipper MVP intentionally deferred that capability.

This keeps assessment tests meaningful across simulator and real hardware instead of letting the simulator claim a broader or differently classified surface.

## Remaining M3 work

This slice establishes the state machine and execution loop. Before M3 is fully complete, the project still needs:

- a user-facing assessment CLI/API that creates, inspects, and resumes assessments;
- richer result rules that derive domain-specific observations from normalized evidence;
- explicit recovery semantics for a persisted `RUNNING` step;
- a first assessment report generated only from persisted state and evidence;
- a real lab run after the four Flipper capabilities are hardware-verified.
