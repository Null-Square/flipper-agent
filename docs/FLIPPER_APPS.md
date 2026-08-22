# Flipper external application integration

## Purpose

Flipper Zero external applications are useful instrument extensions, but an installed `.fap` is not
itself an assessment capability. Hardware Pentest Agent keeps these facts separate:

```text
FAP installed
    != accessory attached
    != accessory firmware healthy
    != assessment capability hardware-verified
```

The app layer therefore provides controlled discovery and lifecycle primitives that app-specific
drivers can build on without exposing Flipper CLI command strings to the assessment engine.

## Known app catalog

The initial catalog contains one application:

- app ID: `esp32_wifi_marauder`
- display name: ESP32 WiFi Marauder
- expected path: `/ext/apps/GPIO/esp32_wifi_marauder.fap`
- expected accessory: an ESP32 board running compatible Marauder firmware

The companion app path follows the upstream WiFi Marauder installation guidance. A future catalog
entry must declare an exact app ID and path before it can use the normal app-manager lifecycle.

## Discovery

`FlipperAppManager` checks only catalogued paths under `/ext/apps`. When an app exists it records:

- the catalogued app identity;
- the exact SD-card path;
- storage metadata returned by stock Flipper CLI;
- the MD5 fingerprint reported by `storage md5`.

The device-provided MD5 is used as a compatibility/fingerprint signal, not as a security signature.
Real capability verification must still retain independent evidence for the complete instrument
state.

## Controlled lifecycle

The app transport uses only typed operations:

- `storage stat <known app path>`;
- `storage md5 <known app path>`;
- `loader info`;
- `loader open <known app path>`;
- `loader close`;
- allow-listed Flipper button events through `input send`.

There is no generic CLI passthrough and the manager cannot launch an arbitrary app ID. App paths are
restricted to `.fap` files below `/ext/apps` and parent traversal is rejected.

Short button input is emitted as the documented sequence:

```text
press -> short -> release
```

Only `up`, `down`, `left`, `right`, `back`, and `ok` are accepted.

## Marauder composite-instrument model

The Wi-Fi MVP is modeled as a composite instrument:

```text
Flipper Zero
  + Marauder companion FAP
  + ESP32 expansion board
  + Marauder board firmware
  + one or more host transport links
        -> typed Wi-Fi assessment capabilities
```

The first robust host configuration may use two simultaneous physical links:

1. Flipper USB for Flipper identity, FAP discovery, and app lifecycle;
2. Dev Board USB/UART for bounded Marauder reconnaissance commands.

This avoids depending on blind menu navigation. A later protobuf/screen-observation transport can
support one-cable UI-driven operation for applications that do not expose a suitable host protocol.

## Safety boundary

The initial Marauder integration will expose only bounded reconnaissance/observation operations.
It will not expose a generic Marauder console, disruptive Wi-Fi attacks, credential collection,
impersonation, or unrestricted packet transmission.

Any later active operation must be modeled as its own typed capability with an appropriate action
class, engagement-policy requirements, approval behavior, evidence contract, and real-hardware
verification procedure.
