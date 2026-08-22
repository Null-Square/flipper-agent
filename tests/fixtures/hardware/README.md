# Hardware Protocol Fixtures

These fixtures are **protocol compatibility inputs**, not hardware-verification evidence.

The `synthetic/` directory contains hand-authored examples that prove the replay machinery itself. After a real controlled lab session, sanitized `TranscriptRecorder` outputs may be promoted into versioned firmware directories such as:

```text
flipper/official-1.4.x/device-info.json
marauder/v1.12.1/probe.json
marauder/v1.12.1/beacon-observation.json
```

Before committing a recorded fixture:

1. capture it through the repository transcript recorder rather than raw terminal logging;
2. inspect the resulting JSON manually;
3. verify UID, MAC addresses and secret values are redacted;
4. keep only the protocol exchange needed for the contract;
5. record the upstream firmware family in the directory/name;
6. run `python scripts/test_harness.py contract`;
7. never copy a hardware-verification record into this directory or claim replay as physical verification.

The replay loader deliberately rejects obvious unredacted Wi-Fi password echoes, Marauder join secrets, Flipper UID lines and MAC addresses. This is a final fixture hygiene check, not a substitute for reviewing a capture before commit.
