# Programmable Hardware Architecture

## Product thesis

Hardware Pentest Agent is not a Flipper command wrapper and it is not a catalog of fixed hardware tools.

The long-term product is a **hardware-native pentesting runtime** that lets an outer agent harness understand connected physical computing resources, choose how to use them for an assessment, compose existing primitives, and synthesize new software or firmware when the required capability does not already exist.

Flipper Zero is provider #1 because it is a practical first platform for proving discovery, physical interfaces, FAP generation, deployment, execution, evidence, and HIL verification. It is not the architectural boundary.

```text
Codex / Null-AI / another agent harness
                  |
                  v
        Hardware Pentest Agent
                  |
        security objective / state
                  |
                  v
            capability need
                  |
       +----------+----------+
       |          |          |
     reuse      compose    synthesize
       |          |          |
       +----------+----------+
                  |
          hardware resolver
                  |
   +--------------+--------------+----------------+
   |              |              |                |
 Flipper        ESP32          RP2040         debug/radio/
   FAP          ESP-IDF        Pico SDK       capture tool
   |              |              |                |
   +--------------+--------------+----------------+
                  |
             physical world
```

## Hardware roles

A physical device can have one or more roles.

### Target

The system being assessed: camera, drone, router, lock, sensor, controller, vehicle module, development board, or another embedded product.

### Hardware provider

A programmable or controllable device the runtime can use to perform measurements or interactions. Examples include Flipper Zero, ESP32 boards, RP2040 boards, STM32 boards, Proxmark3, debug probes, logic analyzers, SDRs, and Linux SBCs.

### Target-provider hybrid

Some hardware can be both the target and a controllable compute substrate. For example, a development board under assessment may expose a bootloader or debug interface that lets the runtime deploy a temporary diagnostic payload. The role must be explicit; gaining control of a target does not automatically make it an authorized provider.

## Board / hardware descriptor

Every programmable provider should eventually expose a normalized `HardwareDescriptor` independent of the vendor SDK.

The descriptor should include:

- stable identity and hardware revision;
- architecture / MCU / SoC family;
- compute and memory constraints relevant to generated tooling;
- GPIO resources and voltage domain;
- UART, SPI, I2C, CAN and other buses;
- radio peripherals such as Wi-Fi, BLE, NFC, Sub-GHz and SDR capabilities;
- USB roles;
- ADC/DAC/timers/PIO/DMA where relevant;
- debug/programming interfaces;
- installed firmware/runtime state;
- supported build toolchains;
- supported artifact types;
- deployment methods;
- reset/recovery method;
- evidence/output channels;
- verified limitations.

Example shape:

```yaml
hardware_id: flipper-zero
architecture: stm32wb55
resources:
  gpio: true
  uart: true
  spi: true
  i2c: true
  infrared_rx: true
  nfc: true
  subghz: true
toolchains:
  - ufbt
artifacts:
  - fap
deployment:
  - flipper_storage_loader
```

The descriptor describes **what can be built or controlled**, not what the assessment should do.

## Capability resolution

When a test requires a capability, the runtime should resolve it in this order:

1. **Reuse** an existing verified capability implementation.
2. **Compose** verified primitives if the capability can be satisfied without new firmware.
3. **Use a mature external tool** through an existing adapter if one already solves the problem.
4. **Generate host-side software** when hardware firmware does not need to change.
5. **Synthesize a board-specific app/firmware payload** using a compatible toolchain backend.
6. **Request a different hardware provider** if the available hardware cannot satisfy the physical requirements.

This prevents the agent from generating code merely because it can.

## Generalized synthesis request

Capability synthesis should become independent of Flipper/FAP.

```text
CapabilitySynthesisRequest
- objective
- required physical interfaces
- timing / bandwidth requirements
- read / interact / transmit / modify requirements
- expected evidence schema
- runtime bounds
- target constraints
- candidate hardware providers
```

A resolver then selects a synthesis backend:

```text
FlipperSynthesisBackend   -> FAP / uFBT
ESP32SynthesisBackend     -> ESP-IDF / PlatformIO
RP2040SynthesisBackend    -> Pico SDK / PIO
STM32SynthesisBackend     -> STM32 HAL / Zephyr / OpenOCD as appropriate
LinuxSBCBackend           -> bounded native process/container
```

The build, deployment and evidence pipeline remains common even though the generated artifact differs.

## Toolchain providers

Build and deployment are separate contracts.

Candidate build providers:

- uFBT / Flipper SDK;
- ESP-IDF;
- PlatformIO;
- Pico SDK;
- Zephyr;
- STM32 toolchains;
- sigrok protocol decoders;
- OpenOCD/GDB automation artifacts.

Candidate deployment providers:

- Flipper storage/loader or structured RPC;
- esptool/serial bootloader;
- UF2 mass-storage deployment;
- DFU;
- OpenOCD/CMSIS-DAP/J-Link;
- vendor bootloaders;
- SSH/container execution for Linux-class boards.

No assessment logic should contain toolchain-specific commands.

## Physical capability graph

The runtime should evolve from a flat capability registry into a graph that can answer:

- what physical resources are available;
- which resources can be combined;
- which board can meet timing/bandwidth/electrical requirements;
- which implementation already exists;
- which implementation can be synthesized;
- what operator setup is required;
- what evidence channel can prove the experiment result.

Example:

```text
need: internal.uart.autodetect
  |
  +-- existing capability? no
  |
  +-- available resources
        Flipper: UART RX + GPIO timing + FAP toolchain
        RP2040: PIO + UART + Pico SDK
  |
  +-- choose provider based on required baud/timing fidelity
  |
  +-- synthesize implementation
  |
  +-- deploy -> execute -> evidence -> verify
```

## Capability memory is executable, not conversational

A successful synthesized capability should be stored as a reusable implementation with:

- normalized capability ID;
- source and artifact hashes;
- hardware descriptor compatibility constraints;
- toolchain/version constraints;
- evidence schema;
- known limitations;
- HIL verification records;
- assessment history.

The next agent session should discover that implementation from the registry rather than relying on model memory.

```text
new need
  -> synthesize
  -> successful HIL
  -> reusable implementation
  -> future registry route
```

This is how the system's hardware competence should grow over time.

## Example target classes

### Camera

The target may expose UART, SPI flash, Ethernet/Wi-Fi, debug pads, removable storage, image sensors and firmware update interfaces. The agent should model the observed interfaces, choose appropriate providers, and synthesize a helper only when existing tooling is insufficient.

### Drone

The target may contain a flight controller, radio link, GNSS, ESC buses, CAN/UART links, companion computer, camera, storage and debug interfaces. The same assessment state can span multiple components and providers without becoming a drone-specific agent.

### Unknown PCB

The workflow may begin with human/vision-assisted component and test-point identification, then move through voltage checks, passive bus observation, protocol identification, debug-interface detection, firmware acquisition and correlated analysis.

## What belongs to the outer agent harness

Codex, Null-AI, or another agent harness may own:

- model inference;
- conversation context;
- generic tool loop;
- generic coding assistance;
- user interaction.

Hardware Pentest Agent owns:

- target/component state;
- hardware descriptors;
- capability graph and implementation registry;
- assessment methodology;
- build/deployment provenance;
- physical execution state;
- evidence and verification;
- resumable assessment state.

The project should therefore remain usable through Python, CLI and MCP without requiring its own generic LLM harness.

## Near-term reference implementation

The next engineering proof remains Flipper-first:

1. complete real Flipper + Marauder HIL certification;
2. make Flipper transport more structured where RPC provides value;
3. persist generated FAP capabilities and promote them after HIL;
4. add the first `HardwareDescriptor` and synthesis backend contracts;
5. refactor the current Flipper synthesis implementation behind those generic contracts;
6. add a materially different programmable provider (preferably RP2040/ESP32 or a debug/capture provider) to prove synthesis portability;
7. perform an assessment where the agent encounters a missing capability, creates it, validates it on hardware, and resumes the assessment.

That experiment is the key milestone: **the agent should solve a physical testing problem that was not pre-implemented as a fixed tool.**
