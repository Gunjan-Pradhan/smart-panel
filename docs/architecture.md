# System Architecture & Technical Specification

**Project:** Smart Load Protection Panel  
**Status:** Architecture Reconciled & Aligned (Post-Audit Baseline)  
**Last Updated:** 2026-11-03  

---

## 1. System Mission & Core Principles

The Smart Load Protection Panel is a dual-channel 230 V AC energy monitoring, appliance recognition, and protection system. It combines deterministic edge hardware protection with intelligent cloud/edge analytics.

### Safety Invariants
1. **Deterministic Edge Protection:** Hardware relays switch autonomously on overcurrent, overvoltage, undervoltage, and meter loss inside the ESP32-S3 firmware. Edge protection never waits for or depends on internet, Wi-Fi, MQTT, or backend servers.
2. **AI Is Strictly Advisory:** Machine learning models, fingerprinting engines, and rule engines advise and suggest; they **never** actuate physical relays or modify hardware safety limits autonomously.
3. **Confirmed Limits Only:** Channel safety limits remain unconfirmed until an authorized human confirms them.
4. **Clean Boundary Separation:** 
   - `panel/{DEVICE_ID}/telemetry/{CH}`: Pure electrical measurement streaming from device to backend.
   - `panel/{DEVICE_ID}/cmd` & `ack`: Authorized control plane with guaranteed state tracking.
   - `panel/{DEVICE_ID}/event`: Hardware and system notifications.

---

## 2. Component Inventory

| Component | Technology | Current Implementation Status | Responsibility |
|---|---|---|---|
| **Protection Panel** | ESP32-S3 + dual PZEM-004T + Relay & SSR | Prototype sketch in `reference/`; Production PlatformIO C++ firmware in **Workstream 2** | Local dual-channel measurement, inrush blanking, 3-strike lockout, local schedules, safe boot |
| **MQTT Broker** | Eclipse Mosquitto 2.0.22 | **Built & Tested** (Docker `127.0.0.1:1883`) | Message transport between firmware/simulator and backend |
| **Backend API** | FastAPI, Python 3.13, SQLAlchemy 2, Pydantic v2 | **Built & Tested (Simulation)** (79 pytest tests) | REST endpoints for auth, device inspection, learning sessions, fingerprints, recognition, anomaly detection, mode enforcement |
| **Database** | PostgreSQL 17 + TimescaleDB 2.31 | **Built & Tested** (Migrations 0001–0005) | Relational source of truth for users, devices, profiles, fingerprints, and telemetry hypertable |
| **Simulator** | Python 3.13 | **Built & Tested (Simulation)** | Isolated synthetic telemetry generator (DOL motor inrush, bulb loads) |
| **Web Dashboard** | React 18, Vite 6 | **Built & Tested (Local UI)** | Live telemetry dials, AI Panel (training, recognition, suggestions, anomalies), Profile management |
| **Background Consumer** | Python / Asyncio MQTT | **Planned (Workstream 5)** | Continuous background ingestion of telemetry, events, and acks into TimescaleDB |

---

## 3. End-to-End Data Flow

```
+-----------------------------------------------------------------------------------+
| PHYSICAL PANEL (ESP32-S3)                                                          |
| - Channel 1 (Induction Motor): PZEM-004T on UART2 | Mechanical Relay (Active-LOW) |
| - Channel 2 (Resistive Bulbs): PZEM-004T on UART1 | SSR-40DA Relay (Active-HIGH)  |
| - Local Protection: Inrush Blanking, 3-Strike Lockout, Overcurrent, Safe Boot    |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          | MQTT (JSON Contract)
                                          v
+-----------------------------------------------------------------------------------+
| ECLIPSE MOSQUITTO BROKER (127.0.0.1:1883)                                         |
| - panel/{DEVICE_ID}/telemetry/{CH} (QoS 1, Unretained)                             |
| - panel/{DEVICE_ID}/status         (QoS 1, Retained LWT)                          |
| - panel/{DEVICE_ID}/event          (QoS 1, Unretained)                            |
| - panel/{DEVICE_ID}/cmd            (QoS 1, Unretained)                            |
| - panel/{DEVICE_ID}/ack            (QoS 1, Unretained)                            |
+-------------------+-------------------------------------+-------------------------+
                    |                                     ^
                    | Subscribes                          | Publishes Commands
                    v                                     |
+---------------------------------------------------------+-------------------------+
| FASTAPI BACKEND (Python 3.13)                                                     |
| - Background Ingestion Service (Edge Glitch Filtering: 50-300V, 0-50A, PF 0-1)    |
| - TimescaleDB Hypertable Persistence (telemetry: v, i, p, pf, f, e)               |
| - 24-Feature Fingerprint Extraction Engine                                        |
| - Real-Time Recognition Engine (Standardized Weighted Euclidean Distance)        |
| - Declarative Mode Suggester (YAML Rules: Motor Protection, Lighting Eco)        |
| - Multi-Tier Anomaly Detector (Rolling Z-Scores, Noise Floors, DOL Inrush Filter) |
| - Mode Enforcer & Always-On Command Safety Guard                                  |
+-------------------+---------------------------------------------------------------+
                    |
                    | REST API (JWT Authenticated, 404 Tenant Isolation)
                    v
+-----------------------------------------------------------------------------------+
| OPERATOR DASHBOARD (React 18 + Vite 6)                                            |
| - Live Instrumentation & Telemetry                                                |
| - AI Intelligence Tab (Session Training, Similarity Confidence, Mode Approvals)   |
| - Profile Catalog & Manual Confirmation                                           |
+-----------------------------------------------------------------------------------+
```

---

## 4. Current Status vs Roadmap

The system has achieved complete backend simulation verification (79 automated tests passing). The following areas represent the active completion roadmap:

1. **Workstream 1 (Current):** Single source of truth documentation reconciliation.
2. **Workstream 2:** ESP32-S3 PlatformIO firmware with FreeRTOS tasks and laptop-native unit tests.
3. **Workstream 3:** Proposed vs. confirmed safety limits policy.
4. **Workstream 4:** Remote control pipeline with command dispatch over MQTT and device acknowledgement tracking.
5. **Workstream 5:** Automatic background MQTT subscriber in FastAPI.
6. **Workstream 6:** Multi-user accounts, registration endpoint, and per-device RBAC roles.
7. **Workstream 7:** On-device schedule synchronization and offline execution.
8. **Workstream 8:** Persistent per-load Isolation Forest models and 0–100 health score calculation.
9. **Workstream 9:** Historical trends, events, and energy (kWh) views in the React dashboard.
10. **Workstream 10:** Multi-tenant fault-injection simulator.
11. **Workstream 11:** Formal bench validation protocols (Protocols A–D) comparing hardware vs simulation.
12. **Workstream 12:** Production hardening, secrets verification, and packaging.
