# Hardware Capability Verification

## Why verification is separate from implementation

Hardware Pentest Agent distinguishes three facts that are easy to blur:

1. an instrument is theoretically capable of an operation;
2. the adapter implements a normalized operation;
3. that implementation was proven against real hardware in a known software state.

Only the third fact is sufficient for normal agent capability discovery.

```text
implemented
    -> hardware_verified
    -> assessment_verified
```

A passing unit test or simulator result cannot promote a physical capability to `hardware_verified`.

## Production trust path

The normal Flipper adapter accepts a verification resolver. The local implementation stores verification data under:

```text
.hardware-pentest/verification/
  records/
  artifacts/
```

The production path is:

```text
real verification procedure
        |
        v
actual typed adapter execution
        |
        v
expected lab result comparison
        |
        v
raw + normalized verification artifact
        |
        +--> SHA-256
        |
        v
immutable verification record
        |
        v
LocalVerificationStore
        |
        +-- exact instrument match
        +-- exact model/kind match
        +-- exact firmware match
        +-- exact adapter-version match
        +-- latest record passed
        +-- evidence file exists
        +-- evidence SHA-256 still matches
        |
        v
capability becomes discoverable
```

If any required condition fails, the capability remains unavailable.

The verifier does not have a generic `mark_verified(capability_id)` path. Each supported capability has a named procedure that executes the same typed handler later used by the assessment runtime.

## Verification record

A record contains:

- schema version;
- record ID;
- capability ID;
- timezone-aware test timestamp;
- pass/fail result;
- exact instrument ID;
- instrument kind and model;
- firmware version;
- adapter version;
- verification procedure ID and version;
- content-addressed evidence reference;
- evidence SHA-256;
- individual check results.

The evidence artifact also captures the procedure parameters, instrument identity, typed action class, normalized result, raw adapter response, limitations, and every pass/fail check.

The store copies the supplied evidence into a content-addressed artifact path. Records are append-only from the application's point of view.

## Conservative invalidation

A verification does not automatically survive software or device changes.

A record must match the current:

- instrument ID;
- instrument kind;
- instrument model;
- firmware version;
- adapter version.

Changing Flipper firmware or changing the adapter version therefore requires re-verification before the capability is exposed again. This is intentionally conservative during development.

## Revocation

For one exact instrument/software state, the latest valid record for a capability wins.

A later failed verification revokes an earlier pass. This makes regressions explicit instead of allowing an old successful test to remain authoritative forever.

## Evidence integrity

Every time capabilities are resolved, the store hashes the retained evidence artifact again. A missing or modified artifact causes the associated passing record to grant nothing.

Malformed records, unsupported schema versions, invalid boolean types, invalid hashes, and artifact references outside the verification directory are ignored fail-closed.

This protects against accidental/stale/corrupt local verification state. It is not yet a cryptographic identity/signature system against a privileged local attacker. Signed verification manifests and centralized attestation can be added later if Null-AI needs distributed trust.

## Controlled Flipper procedures

All procedures require a real, known lab condition. The operator must explicitly confirm that condition before execution.

### Infrared receive

Use a lab-owned IR source that emits a known protocol:

```bash
hardware-pentest flipper-verify \
  --port <PORT> \
  infrared \
  --expected-protocol NEC \
  --confirm-known-source
```

The procedure passes only when `infrared.observe` executes successfully and the normalized decoded observations contain the expected protocol.

### Sub-GHz receive

Use a lab-owned source at an allowed receive frequency:

```bash
hardware-pentest flipper-verify \
  --port <PORT> \
  subghz \
  --frequency-hz 433920000 \
  --expected-protocol Princeton \
  --confirm-known-source
```

This procedure is receive-only and continues to use the internal CC1101 path. It does not transmit or replay anything.

### NFC identification

Place a known lab-owned NFC tag in the reader field:

```bash
hardware-pentest flipper-verify \
  --port <PORT> \
  nfc \
  --expected-protocol "Mifare Ultralight" \
  --confirm-known-source
```

The procedure invokes only the bounded protocol-identification capability. It does not read application data, write, clone, emulate, or attack keys.

### GPIO inspection

GPIO verification requires a prepared non-debug input pin and a known digital level. Before connecting the target or level source, the operator must confirm:

- the selected pin is already configured as input;
- common ground is connected;
- the applied voltage is safe for Flipper Zero;
- the expected level is intentionally applied.

Then run:

```bash
hardware-pentest flipper-verify \
  --port <PORT> \
  gpio \
  --pin PA7 \
  --expected-level 1 \
  --confirm-setup
```

The assessment/verifier path issues only `gpio read <PIN>`. It never calls `gpio mode`, `gpio set`, or any output-driving operation.

## Result semantics

A verification attempt always records what actually happened after execution begins.

- expected observation found: passing record;
- capability executes but the expected observation does not match: failed record;
- a later failed record for the same exact device/software state revokes an earlier pass.

A missing physical confirmation is rejected before hardware execution and does not create a synthetic record.

The CLI exits non-zero when an executed verification procedure produces a failed record.

## Test/development override

The adapter retains an explicit test-only verification override so deterministic fake-hardware tests can exercise implemented operations before physical hardware is available.

It cannot be used accidentally:

```python
FlipperAdapter(
    port,
    verified_capabilities={"infrared.observe"},
    allow_verification_override=True,
)
```

Supplying `verified_capabilities` without the explicit opt-in raises an error. Production construction should use a verification resolver instead.

## CLI inspection

Show the exact connected Flipper and which implemented capabilities are currently verified:

```bash
hardware-pentest flipper-capabilities --port <PORT>
```

Use a different verification store if required:

```bash
hardware-pentest flipper-capabilities \
  --port <PORT> \
  --verification-root /path/to/verification
```

Inspect verification records and current artifact integrity:

```bash
hardware-pentest verification-records
```

There is intentionally no generic CLI command that lets an operator manually mark an arbitrary capability as passed. A capability-specific verification procedure must execute and produce the evidence and record.

## Current release claim

The four v0.1 Flipper capability families are implemented in code, but release documentation must continue to describe them as hardware-unverified until these procedures have been run successfully on a real supported Flipper Zero and the resulting evidence has been reviewed.
