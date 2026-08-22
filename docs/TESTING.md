# Testing and Hardware-in-the-Loop Strategy

Hardware Pentest Agent is a hardware harness, so a green unit suite is necessary but insufficient. The same behavior must be exercised through progressively more realistic layers without making ordinary development depend on attached devices.

## Named profiles

Use the repository test launcher:

```bash
python scripts/test_harness.py quick
python scripts/test_harness.py contract
python scripts/test_harness.py ci
python scripts/test_harness.py hil
```

### `quick`

Fast local feedback. Runs lint plus tests that are neither protocol-contract nor hardware-in-the-loop tests. Use while editing.

### `contract`

Runs deterministic protocol and fault-injection contracts. These tests model serial fragmentation, partial writes, disconnects, malformed responses, protocol drift and other behavior that a perfect mock normally hides. No physical hardware is opened.

### `ci`

The merge gate: full lint plus every non-HIL test. GitHub Actions should use the same semantics so local and remote gates do not diverge.

### `hil`

Opt-in tests that may open real USB serial devices. The launcher refuses to run this profile unless:

```bash
export HPA_HIL=1
```

Configure devices explicitly; discovery alone never authorizes a hardware test:

```bash
export HPA_FLIPPER_PORT=/dev/ttyACM0
export HPA_MARAUDER_PORT=/dev/ttyUSB0
python scripts/test_harness.py hil
```

Install hardware dependencies for HIL work:

```bash
python -m pip install -e ".[dev,flipper]"
```

## Test pyramid

```text
                 physical HIL
              known lab fixtures
             /                  \
       recorded/contract tests
      protocol + fault injection
     /                          \
  adapter / policy / state / evidence
 /                                \
unit tests, parsers, models, validation
```

Ordinary CI must never require hardware. HIL evidence must never be fabricated by a software test.

## Required failure coverage for hardware-facing changes

A new transport or physical capability should cover the relevant subset of:

- fragmented serial delivery;
- short/partial write;
- read/write I/O failure;
- response timeout;
- response-size bound;
- malformed output;
- wrong device identity;
- firmware or FAP identity change;
- disconnect/reconnect;
- stale preflight record;
- tampered verification/evidence artifact;
- cleanup failure;
- unsafe or out-of-range input;
- unrelated running application;
- secret redaction;
- negative/inconclusive physical observation.

Tests should fail closed. A protocol parse failure must not silently become a successful observation.

## Recorded-device contracts

During a real lab session, sanitize useful device transcripts and promote stable protocol shapes into contract fixtures. Fixtures are compatibility samples, not hardware-verification evidence.

Never commit:

- Wi-Fi passwords or secret values;
- unrelated device data;
- user/account identifiers;
- raw credential material unless a test explicitly requires a synthetic sample;
- a real hardware-verification record presented as if CI produced it.

A future fixture layout should be versioned by provider/firmware, for example:

```text
tests/fixtures/hardware/
  flipper/
    official-1.4.x/
      device-info.txt
      loader-idle.txt
  marauder/
    v1.12.1/
      help.txt
      beacon-list.txt
```

## Deterministic lab fixture

The physical rack should use known stimuli rather than the surrounding RF environment. Initial fixtures:

- Flipper Zero with known firmware;
- compatible ESP32 Marauder board with stable USB identity;
- `NULLSQUARE-HIL-AP` on a fixed lab channel;
- controlled network host with one known service;
- known NFC tag;
- known IR source;
- safe prepared GPIO level;
- later a controlled Sub-GHz source where lawful and appropriate.

The assertion is `known fixture observed`, not `some random environmental signal was seen`.

## Release gates

A change that touches only pure models may merge with the normal CI gate. A change that alters a hardware protocol, firmware compatibility assumption, FAP deployment, generated-app runtime, or physical capability must additionally be exercised in the lab before a release is labelled hardware-verified.

Recommended release flow:

```text
code
  -> quick tests
  -> contract tests
  -> full non-HIL CI
  -> physical preflight
  -> deterministic HIL suite
  -> verified capability matrix
  -> release
```

## Agent/Codex operation

`AGENTS.md` is the authoritative local-agent runbook. A coding agent should use the named profiles and high-level typed CLI instead of creating an ad-hoc pyserial script. Real hardware is opt-in through `HPA_HIL=1` and explicit port variables.

This makes it safe to ask a local coding agent to perform tasks such as:

```text
Run the quick suite.
Run the contract suite and explain any failure.
With the attached lab Flipper, run the HIL smoke suite.
Run preflight and tell me which capabilities are actually verified.
```

The agent should never convert a simulator/contract success into a `hardware_verified` claim.
