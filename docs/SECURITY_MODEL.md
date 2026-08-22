# Security Model

## Purpose

Hardware Pentest Agent controls physical security instruments. A model error can create effects outside the software process.

The security model therefore treats the LLM as an untrusted planner. Deterministic runtime controls enforce authorization, action risk, instrument constraints, and evidence requirements.

## Security principles

1. Authorization is explicit.
2. Scope is machine-readable.
3. The model cannot bypass policy.
4. Device adapters expose typed operations, not unrestricted command channels.
5. Passive observation is the default.
6. Active and state-changing actions need stronger gates.
7. Physical constraints are validated before execution where possible.
8. Human physical work is explicit.
9. Evidence and provenance are retained.
10. Failure must stop safely.

## Trust boundaries

```text
Untrusted / advisory
--------------------
LLM plan
LLM interpretation
user-provided natural language
third-party target metadata

Deterministic control boundary
------------------------------
engagement parser
schema validation
policy engine
approval state
constraint validators
capability router
adapter allowlist

Physical execution boundary
---------------------------
instrument adapter
transport
device
physical target
```

The agent can recommend. The runtime decides whether an action can execute.

## Authorization model

An assessment requires an engagement record.

The engagement record must identify:

- engagement identifier;
- target identifiers;
- validity period;
- allowed and denied capability patterns;
- maximum action class;
- approval rules;
- operator notes and constraints.

The runtime must reject expired engagements.

The runtime must reject actions against targets that are not in scope.

An engagement record is a technical control. It does not replace contracts, written authorization, regulatory review, or local legal requirements.

## Action classes

### OBSERVE

Passive or read-only collection that does not intentionally modify the target.

Examples:

- read device information;
- observe an NFC/RFID interface;
- passive RF observation;
- capture already-present serial output.

Default: can be allowed by engagement policy.

### INTERACT

Bounded protocol interaction that may cause the target to respond but is not intended to change persistent state.

Default: explicit scope required.

### TRANSMIT

Intentional radio or infrared transmission.

Default: blocked in MVP unless a future policy explicitly permits the exact operation and environment.

### MODIFY

Changes target or assessment-relevant instrument state.

Default: operator approval required and deferred from MVP.

### EMULATE

Emulates an authorized signal, card, tag, remote, or device identity.

Default: blocked in MVP.

### DESTRUCTIVE

Fault injection, invasive extraction, physical modification, or any operation with material risk of damage or loss.

Default: disabled.

## Policy decision

Every action receives exactly one decision:

```text
ALLOW
REQUIRE_APPROVAL
REQUIRE_HUMAN_ACTION
DENY
```

A `DENY` decision cannot be overridden by the agent.

A `REQUIRE_APPROVAL` decision needs an approval token or persisted operator approval associated with the exact action or approved action class.

A `REQUIRE_HUMAN_ACTION` decision must identify what the person must do and what state the runtime needs before it can continue.

## Deny precedence

Deny rules take precedence over allow rules.

Example:

```yaml
allowed_capabilities:
  - wireless.nfc.*
denied_capabilities:
  - wireless.nfc.emulate
```

`wireless.nfc.emulate` is denied.

## Adapter safety

Adapters must use an allowlist of implemented operations.

Adapters must not expose unrestricted command execution through the normal runtime API.

If an adapter needs a CLI internally, it must:

- construct the command from validated typed fields;
- avoid user-controlled command concatenation;
- map timeouts and errors into normalized results;
- capture the executed normalized operation for evidence;
- reject unsupported parameters before transport execution.

## Physical constraints

Hardware actions can have electrical, RF, timing, and state constraints.

A capability descriptor can declare constraints such as:

- supported voltage range;
- supported frequency range;
- receive-only requirement;
- connection prerequisite;
- target power-state requirement;
- human measurement requirement;
- timeout;
- safe retry count.

If the runtime cannot validate a required constraint, it must stop or request a human action.

It must not guess.

## RF policy

Radio rules vary by jurisdiction, frequency, power, equipment, and purpose.

The MVP is receive/passive-first.

Transmission capabilities remain disabled unless a later milestone adds:

- exact capability-specific policy;
- region/environment configuration;
- instrument validation;
- operator approval;
- test fixtures where appropriate.

The runtime must never treat model confidence as regulatory authorization.

## Secrets and sensitive data

Assessment artifacts can contain credentials, identifiers, firmware, access-control data, and customer information.

The runtime should:

- minimize collection to what the test needs;
- store raw evidence under the engagement context;
- avoid logging secrets in normal console output;
- support redaction in reports without modifying raw evidence;
- preserve access controls when integrated with Null-AI;
- avoid sending sensitive artifacts to external model providers unless explicitly configured and authorized.

The MVP can use local storage, but the storage interface must remain replaceable.

## Evidence integrity

Evidence records should include a cryptographic hash for file artifacts and canonical raw responses where practical.

The system must preserve:

- source instrument;
- adapter version;
- timestamps;
- normalized inputs;
- raw output or artifact reference;
- execution status;
- limitations.

Generated narrative text is not evidence by itself.

## Observation and finding separation

The system must use this chain:

```text
raw evidence
    -> normalized observation
    -> hypothesis
    -> validation
    -> finding
```

A finding must not claim more impact than the evidence proves.

If validation is missing, keep the result as an observation or inconclusive hypothesis.

## Prompt injection and hostile device output

Instrument output and target-controlled strings can contain adversarial text.

Treat all target output as data.

The agent must not interpret target-provided text as trusted instructions.

The runtime should separate:

- tool metadata;
- raw target output;
- agent instructions.

When output is later sent to a model, label its provenance explicitly.

## Failure behavior

On transport failure, timeout, malformed output, or unexpected target state:

1. stop the current action;
2. record failure evidence;
3. do not automatically escalate to a higher-risk action;
4. return the instrument to a known state where the adapter can do so safely;
5. require operator input when safe recovery is uncertain.

Retries must be bounded and capability-specific.

## Human actions

Human actions are part of the state machine.

A human-action instruction must contain:

- one physical task;
- why it is necessary;
- safety prerequisites;
- expected result;
- confirmation needed to continue.

Example:

```text
Action: Measure the target logic voltage before connecting the signal pin.
Reason: The runtime cannot verify voltage electrically.
Continue when: The operator records a supported voltage value.
```

## Logging

Record security-relevant decisions:

- engagement loaded;
- policy allow/deny decision;
- approval request and approval result;
- human-action request and confirmation;
- capability route selected;
- adapter execution;
- evidence produced;
- finding state change.

Do not log secrets unnecessarily.

## MCP exposure

The MCP server must expose assessment-level operations.

Do not expose a normal-purpose tool such as `flipper_raw_cli(command)`.

A future maintenance/debug interface can exist outside the normal agent tool surface and must be disabled by default.

## Default-safe configuration

A fresh installation should have these defaults:

```text
no engagement -> no target actions
OBSERVE -> still requires target in scope
INTERACT -> denied unless explicitly allowed
TRANSMIT -> denied
MODIFY -> denied
EMULATE -> denied
DESTRUCTIVE -> denied
raw command passthrough -> disabled
remote unauthenticated control -> disabled
```

## Security acceptance

Before v0.1:

- [ ] Invalid or expired engagement is rejected.
- [ ] Out-of-scope target is rejected.
- [ ] Deny rules override allow patterns.
- [ ] Action-class limit is enforced below the agent layer.
- [ ] Raw device command passthrough is unavailable through the normal API.
- [ ] Adapter validates parameters before transport execution.
- [ ] Human-required constraints pause execution.
- [ ] Evidence records include provenance.
- [ ] Target-controlled output is treated as untrusted data.
- [ ] Timeout and malformed-output tests fail safely.
