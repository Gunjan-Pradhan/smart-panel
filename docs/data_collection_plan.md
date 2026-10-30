# Hardware-in-the-Loop Data Collection Plan & Validation Protocol

**Project:** Smart Load Protection Panel with Dual Independent 230 V AC Channels  
**Institution:** Final-Year ECE Engineering Project  
**Date:** 2026-10-30  
**Target Hardware:** ESP32-S3 WROOM-1 + 2× PZEM-004T v4 Energy Meters + Relay Protection Board  

---

## 1. Executive Summary & System Architecture

This protocol specifies the rigorous laboratory testing procedure for acquiring electrical telemetry, characterizing appliances, verifying edge filtering, and validating AI load recognition and anomaly detection on the dual-channel smart protection panel.

```
       +-------------------------------------------------------------+
       |               230 V AC Single-Phase 50 Hz Mains             |
       +-------------------------------------------------------------+
                           |                               |
                   [Channel 1 - Industrial]        [Channel 2 - Household]
                           |                               |
                     Relay (GPIO 6)                  SSR (GPIO 38)
                      (Active-LOW)                    (Active-HIGH)
                           |                               |
                    PZEM-004T v4 (Ch 1)             PZEM-004T v4 (Ch 2)
                    UART2: RX=4, TX=5               UART1: RX=44, TX=43
                           |                               |
       +-------------------------------------------------------------+
       |             ESP32-S3 Microcontroller (Local Guard)          |
       |  - 10 Hz Modbus RTU Polling                                 |
       |  - Local Hardware Overcurrent & Overvoltage Cutoff          |
       |  - Wi-Fi MQTT Publisher (energy/dual_pzem/circuit{1,2}/...)  |
       +-------------------------------------------------------------+
                                     |
                                  (MQTT)
                                     v
       +-------------------------------------------------------------+
       |                  Host Edge / Cloud Services                 |
       |  - Mosquitto Broker (127.0.0.1:1883)                        |
       |  - Node-RED (WebSocket /ws/energy -> React Live View)       |
       |  - Python Backend (FastAPI + TimescaleDB + ML Engine)       |
       +-------------------------------------------------------------+
```

---

## 2. Channel Hardware Specifications & Polarities

| Parameter | Channel 1: Industrial Load | Channel 2: Household Load |
|---|---|---|
| **Primary Appliance** | 125 W Single-Phase Induction Motor | Resistive Incandescent/Halogen Bulbs (60W, 100W, 200W) |
| **PZEM Meter** | PZEM-004T v4 (Address 0x01) | PZEM-004T v4 (Address 0x02) |
| **ESP32 Serial Bus** | UART2 (RX: GPIO 4, TX: GPIO 5) | UART1 (RX: GPIO 44, TX: GPIO 43) |
| **Switching Element** | Mechanical Relay (Active-LOW: 0=ON, 1=OFF) | Solid State Relay (Active-HIGH: 1=ON, 0=OFF) |
| **Relay Control Pin** | GPIO 6 (`CH1_RELAY_ACTIVE_LOW true`) | GPIO 38 (`CH2_RELAY_ACTIVE_LOW false`) |
| **Nominal Power** | ~125 W (Active), ~140 var (Reactive) | 60 W to 200 W (Active), < 10 var (Reactive) |
| **Nominal Current** | ~0.82 A RMS | 0.26 A to 0.87 A RMS |
| **Power Factor** | 0.60 to 0.72 (Inductive, Lagging) | 0.98 to 1.00 (Resistive, Unity) |

---

## 3. Mandatory Electrical Safety Boundaries

> [!CAUTION]
> **High Voltage Hazard (230 V AC RMS):**
> 1. All mains terminal blocks, relay contacts, and current transformers must be enclosed inside an insulated, flame-retardant chassis.
> 2. The panel earth ground terminal MUST be bonded directly to utility protective earth (PE) before powering on.
> 3. AI engine outputs are **ADVISORY ONLY**; the AI cannot directly actuate relays or modify local ESP32 trip limits.
> 4. Physical circuit breaker (MCB Type C, 6A) upstream of the panel must remain active during all tests.

---

## 4. Laboratory Test Protocols

### Protocol A: Baseline Zero-Load & Noise Floor Calibration
* **Objective:** Verify sensor health, calibrate idle voltage noise floors, and confirm zero-current isolation.
* **Pre-conditions:** Both relays open (`OFF`); no load connected to socket terminals.
* **Steps:**
  1. Energize panel from 230 V AC mains. Verify ESP32 powers on and establishes Wi-Fi link.
  2. Record 120 consecutive samples (2 minutes at 1 Hz).
  3. Validate that current $I \le 0.02\text{ A}$ and active power $P \le 1.0\text{ W}$ on both channels.
  4. Verify that no CRC errors or Modbus framing glitches occur during idle state.

### Protocol B: Channel 1 Induction Motor Testing
* **Objective:** Capture motor direct-on-line (DOL) inrush transient, steady-state running signature, and mechanical stall envelope.
* **Appliance:** 125 W single-phase capacitor-start induction motor.
* **Steps:**
  1. Connect motor to Socket 1.
  2. Initiate Learning Session via dashboard: `POST /channels/1/learning/start`.
  3. **Stage B1 (Cold Start):** Turn Relay 1 ON. Observe starting inrush current ($I_{\text{peak}} \approx 3.0\text{--}4.5\text{ A}$ for $\approx 1.2\text{ s}$). Verify that the inrush filter suppresses false overcurrent trips.
  4. **Stage B2 (Steady-State Run):** Allow motor to run unloaded for 3 minutes. Record nominal metrics ($V \approx 230\text{ V}, I \approx 0.82\text{ A}, P \approx 125\text{ W}, \text{PF} \approx 0.66, Q \approx 140\text{ var}$).
  5. **Stage B3 (Session Finalization):** Finalize learning session. Confirm extracted fingerprint has $\text{CV}_P \le 0.15$ and status transitions to `ready`.
  6. **Stage B4 (Mechanical Stall Simulation):** Apply mechanical braking friction to motor shaft (or simulate step overload). Verify that current exceeding $1.23\text{ A}$ ($1.5 \times I_{\text{nom}}$) sustained past $2.5\text{ s}$ immediately triggers `mode_alert_stall` in Protection Mode.

### Protocol C: Channel 2 Household Load Testing
* **Objective:** Capture step-wise resistive combinations, verify near-zero reactive power, and test curfew energy tracking in Eco Mode.
* **Appliance:** Bank of incandescent bulbs (60 W bulb, 100 W bulb, 200 W parallel combination).
* **Steps:**
  1. Connect 100 W bulb to Socket 2. Turn Relay 2 ON.
  2. Observe steady draw ($I \approx 0.43\text{ A}, P \approx 100\text{ W}, \text{PF} \ge 0.99, Q \le 5\text{ var}$).
  3. Switch in parallel 100 W bulb ($P \rightarrow 200\text{ W}, I \rightarrow 0.87\text{ A}$). Verify that reactive ratio $Q/S$ remains $< 0.05$.
  4. Run recognition engine: `POST /channels/2/recognize`. Verify match score $> 90\%$ against resistive profile and classification reports `recognized`.
  5. Test Eco Mode curfew validation: Inject timestamp during curfew window (02:00) and verify that `mode_advisory_curfew` event is logged.

### Protocol D: Cross-Channel Simultaneous Load & Voltage Sag Test
* **Objective:** Validate that simultaneous switching on Channel 1 does not cause communication drops, crosstalk, or false trips on Channel 2.
* **Steps:**
  1. Operate Channel 2 with 200 W steady lighting load.
  2. Cycle Channel 1 motor ON and OFF every 30 seconds for 5 iterations.
  3. Monitor Channel 2 voltage sag ($\Delta V$) and verify Channel 2 PZEM UART1 communication error count remains zero.

---

## 5. Automated Data Quality & Framing Glitch Filter

Due to Modbus RTU byte-shift glitches during physical relay contact arcing, raw telemetry must pass validation before persistence or training.

```
Incoming Modbus Packet
          |
   [CRC Checksum Valid?] -- No --> Discard & Log CRC Error
          | Yes
   [Physical Bounds Check]
   - Voltage: 180.0 V <= V <= 270.0 V
   - Current: 0.0 A <= I <= 30.0 A
   - Active Power: 0.0 W <= P <= 6500.0 W
   - Power Factor: 0.0 <= PF <= 1.0
   - Frequency: 45.0 Hz <= f <= 65.0 Hz
          |
         Pass --> Persist to TimescaleDB & Forward to AI Engine
          |
         Fail --> Discard packet; log to exclusion_reasons in DB
```

---

## 6. Success & Evaluation Acceptance Criteria

| Metric | Target Acceptance Threshold | Validation Method |
|---|---|---|
| **Data Retention Rate** | $\ge 98.0\%$ valid packets | Audited historical & live telemetry |
| **Inrush False Alarm Rate** | $0.0\%$ false critical trips during DOL start | Inrush transient filter with $\le 2.0\text{ s}$ window |
| **Load Discrimination** | 100% correct separation between Motor & Bulbs | Standardized Euclidean distance ($D_{\text{motor-bulb}} > 3.0$) |
| **Fingerprint Stability** | $\text{CV}_P \le 0.35$ for steady loads | Coefficient of variation calculation |
| **End-to-End Latency** | $< 500\text{ ms}$ (PZEM read to DB/Dashboard) | Ingestion timestamp delta |
| **Tenant Isolation** | 100% 404 rejection on cross-account access | REST API ownership verification |

---

## 7. Laboratory Checklist & Sign-Off Sheet

- [ ] Visual inspection of mains wiring, fuses, and relay polarities completed.
- [ ] Protective earth grounding continuity verified ($R_{\text{ground}} < 0.5\ \Omega$).
- [ ] ESP32 firmware flashed with correct UART pinouts (`CH1_UART2`, `CH2_UART1`).
- [ ] PostgreSQL + TimescaleDB container healthy and migrations at head (`0005`).
- [ ] Mosquitto MQTT broker running on `127.0.0.1:1883`.
- [ ] Baseline Protocol A executed and verified zero-load stability.
- [ ] Induction Motor Protocol B executed and fingerprint stored.
- [ ] Household Bulbs Protocol C executed and Eco Mode curfew verified.
- [ ] Cleaned CSVs backed up with cryptographic SHA-256 signatures.

