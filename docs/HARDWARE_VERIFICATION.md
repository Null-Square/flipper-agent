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
raw verification artifact
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

There is intentionally no generic CLI command that lets an operator manually mark an arbitrary capability as passed. A capability-specific verification procedure must produce the evidence and record.

## Next procedures

The first capability-specific real-hardware procedures should cover:

- `infrared.observe` with a known IR source;
- `wireless.subghz.observe` with a lab-owned known transmitter at an allowed receive frequency;
- `wireless.nfc.identify` with a known lab-owned NFC tag.

Each procedure should test both the successful observation path and the relevant safe failure/inconclusive path before creating a passing verification record.
