# Hardware Specification and Pinout Notes

**Status:** Authoritative hardware baseline confirmed for final-year ECE project.
**Target Hardware:** ESP32-S3 dual-channel AC protection panel.

---

## 1. Hardware Overview

The Smart Load Protection Panel monitors and controls two independent 230 V AC electrical circuits. Each circuit is instrumented with an independent energy meter and controlled by an isolated switching element.

```
                      +-------------------+
                      |   ESP32-S3 SoC    |
                      +---------+---------+
                                |
             +------------------+------------------+
             | (UART2: GPIO 4/5)                   | (UART1: GPIO 44/43)
             | (Relay: GPIO 6)                     | (SSR: GPIO 38)
             v                                     v
   +-------------------+                 +-------------------+
   | Channel 1: Motor  |                 | Channel 2: Bulbs  |
   | PZEM-004T v3/v4   |                 | PZEM-004T v3/v4   |
   | Electromagnetic   |                 | Solid State Relay |
   | Relay (Active-LOW)|                 | (Active-HIGH)     |
   +-------------------+                 +-------------------+
             |                                     |
      ~125 W Motor                         60 W - 200 W Bulbs
      (Inductive Load)                     (Resistive Load)
```

---

## 2. Channel Hardware Specification Table

| Attribute | Channel 1: Industrial Load | Channel 2: Household Load |
|---|---|---|
| **Primary Appliance** | ~125 W Single-Phase Induction Motor | 60 W to 200 W Incandescent / Halogen Bulbs |
| **Load Characteristics** | Inductive, lagging PF (0.60–0.72), DOL inrush (3–6x for 1.2–2.0 s) | Resistive, near-unity PF (0.98–1.00), minimal cold-filament transient (< 50 ms) |
| **Power Meter Module** | Peacefair PZEM-004T (v3 / v4 compatible) | Peacefair PZEM-004T (v3 / v4 compatible) |
| **Modbus Slave Address** | `0x01` (or isolated on bus) | `0x02` (or isolated on bus) |
| **Microcontroller Serial** | Hardware Serial 2 (UART2) | Hardware Serial 1 (UART1) |
| **ESP32-S3 RX Pin** | **GPIO 4** (connects to PZEM TX) | **GPIO 44** (connects to PZEM TX) |
| **ESP32-S3 TX Pin** | **GPIO 5** (connects to PZEM RX via level shift if needed) | **GPIO 43** (connects to PZEM RX via level shift if needed) |
| **Serial Parameters** | 9600 baud, 8 data bits, no parity, 1 stop bit (8-N-1) | 9600 baud, 8 data bits, no parity, 1 stop bit (8-N-1) |
| **Switching Element** | **Electromagnetic Relay** (SPDT Mechanical, 10A/250V AC) | **Solid-State Relay** (Zero-Crossing SSR-40DA, 40A/250V AC) |
| **Actuation Pin** | **GPIO 6** | **GPIO 38** |
| **Actuation Polarity** | **ACTIVE-LOW (`0 = ENERGIZED / ON`, `1 = OFF`)** | **ACTIVE-HIGH (`1 = ENERGIZED / ON`, `0 = OFF`)** |
| **Boot Safety Level** | Must drive **HIGH** at boot before configuring pin as output | Must drive **LOW** at boot before configuring pin as output |
| **Switching Rationale** | Mechanical contact avoids SSR leakage current on inductive coils | Silent, zero-cross solid-state switching for resistive lighting |
| **Nominal Operating Current** | ~0.82 A RMS steady-state | 0.26 A to 0.87 A RMS |
| **Nominal Active Power** | ~125 W RMS | 60 W to 200 W RMS |
| **Nominal Reactive Power** | ~140 var (Inductive) | < 10 var |

---

## 3. Peripheral Pinout Mapping (Buttons and Indicators)

The following GPIO assignments are designated for firmware status indicators and local operator control:

| Peripheral | GPIO Pin | Circuit / Purpose | Electrical Configuration |
|---|---|---|---|
| **LED 1 (System / Wi-Fi)** | GPIO 10 | Status indicator (Blink = Connecting, Solid = Online, Rapid = Fault) | Active-HIGH with 330 ohm current-limiting resistor |
| **LED 2 (Ch 1 Relay State)** | GPIO 11 | Channel 1 ON / OFF / Fault indicator | Active-HIGH with 330 ohm current-limiting resistor |
| **LED 3 (Ch 2 Relay State)** | GPIO 12 | Channel 2 ON / OFF / Fault indicator | Active-HIGH with 330 ohm current-limiting resistor |
| **Button 1 (Learn Mode)** | GPIO 13 | Trigger load learning session locally | Push-button to GND, internal pull-up enabled |
| **Button 2 (Reset / Safe)** | GPIO 14 | Clear latched fault / Force offline-safe mode | Push-button to GND, internal pull-up enabled |

---

## 4. Hardware Safety Invariants

1. **Relay Glitch Prevention at Boot:**
   The ESP32 GPIO initialization routine must write the idle logic level to the output register **prior** to setting `pinMode(pin, OUTPUT)`.
   - GPIO 6 (Active-LOW): `digitalWrite(6, HIGH)` THEN `pinMode(6, OUTPUT)`
   - GPIO 38 (Active-HIGH): `digitalWrite(38, LOW)` THEN `pinMode(38, OUTPUT)`
2. **Deterministic Autonomous Protection:**
   The microcontroller enforces trip limits and inrush blanking locally in FreeRTOS firmware tasks. If Wi-Fi, the MQTT broker, or the backend fails, local safety protection remains 100% operational.
3. **No SSR Auxiliary Feedback:**
   The SSR-40DA lacks physical auxiliary feedback contacts. Therefore, `relay: true/false` reported over MQTT indicates **commanded state**, which must be verified against current flow (`i > 0.05 A`) before confirming physical load energization.

