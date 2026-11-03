# Smart Load Protection Panel

## Project Overview

An AI-based energy management and optimization system designed to monitor electrical loads, detect abnormal operating behaviour, assess load health, and support safer, more efficient energy usage.

## Project Objectives

- Monitor electrical parameters from connected loads.
- Apply deterministic rules for electrical protection.
- Control load isolation through the protection system.
- Detect abnormal energy-consumption patterns using AI.
- Estimate load health from monitored behaviour.
- Provide a dashboard for monitoring and analysis.

## Technology Stack

- **Firmware:** C++ with PlatformIO
- **Microcontroller:** ESP32-S3
- **Electrical monitoring:** PZEM-004T V4
- **Messaging:** MQTT with Mosquitto
- **Backend:** Python and FastAPI
- **Database:** PostgreSQL with TimescaleDB
- **AI/ML:** NumPy, Pandas, and scikit-learn
- **Dashboard:** React with Vite
- **Containerization:** Docker Compose

## Project Structure

- `backend/` — Backend API and application logic
- `dashboard/` — Web dashboard
- `docs/` — Project documentation
- `firmware/` — ESP32 firmware
- `ml/` — AI models and anomaly-detection logic
- `mosquitto/` — MQTT broker configuration
- `simulator/` — Simulated electrical-load data
- `scripts/` — Local development and verification scripts
- `requirements.txt` — Runtime Python dependencies (exact pins)
- `requirements-dev.txt` — Runtime plus test tooling

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — components, data flow, trust boundaries and known gaps
- [docs/hardware_notes.md](docs/hardware_notes.md) - confirmed hardware pinouts, UART mapping and relay polarity
- [`docs/mqtt_contract.md`](docs/mqtt_contract.md) — authoritative MQTT topics, JSON schemas, command acknowledgements and safety rules
- [`docs/database_schema.md`](docs/database_schema.md) — implemented database schema, ownership rules and migration plan
- [`docs/dependencies.md`](docs/dependencies.md) — Phase 2 dependency record and verified compatibility evidence (installed 2026-10-28)
- [`docs/testing.md`](docs/testing.md) — reproducible test procedures, recorded results and known limitations

## Python Dependencies (Phase 2)

The existing virtual environment is used; do not create a second one.

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
```

Expected: `pip check` prints `No broken requirements found.`

## Local MQTT Broker (Phase 1)

The first infrastructure component is the Mosquitto MQTT broker. It is bound to
`127.0.0.1` on the Windows host and allows anonymous clients for **local
development only**.

```powershell
docker compose up -d mosquitto
docker compose ps
.\.venv\Scripts\python.exe .\scripts\mqtt_smoke_test.py
```

Expected smoke-test result: two `PASS` lines and exit code `0`. Stop the broker with:

```powershell
docker compose down
```

The broker persists retained messages in the Docker volume
`smart-panel-mosquitto-data`. Backend and dashboard services are added in later
phases, one at a time.

## Local Database (Phase 2 — implemented)

`docker-compose.yml` defines a `db` service, bound to `127.0.0.1:5432` with a
named volume. Because Docker Hub's CDN is blocked on this network, the image is
built locally from AWS ECR's official PostgreSQL mirror plus the official
TimescaleDB apt repository (see `db/Dockerfile`). Switching back to the official
`timescale/timescaledb:2.31.0-pg17` image is documented in the Compose comments.

```powershell
Copy-Item .env.example .env      # then change DATABASE_PASSWORD and JWT_SECRET
docker compose build db
docker compose up -d db
docker compose ps
docker compose exec db pg_isready -U smart_panel_user -d smart_panel
```

Use `127.0.0.1` (not `localhost`) for `DATABASE_HOST` on Windows. Docker
publishes the port on IPv4 only, while `localhost` resolves to IPv6 `::1`
first and can stall for the full OS timeout before falling back.

Verified on 2026-10-28: PostgreSQL 17.11, TimescaleDB 2.31.0, hypertable creation,
survival across restart and container recreation, and host connection with
`psycopg`. Details: [`docs/testing.md`](docs/testing.md) T-DB-001/T-DB-002.

### Apply the schema

Alembic owns the schema; do not use `Base.metadata.create_all()`.

```powershell
cd backend
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\alembic.exe current
cd ..
```

Migrations:

- `0001` — TimescaleDB extension
- `0002` — `users`, `refresh_tokens`
- `0003` — `devices`, `loads`, `channels`, `events`, `commands`, `schedules`, `audit_log`
- `0004` — `telemetry` hypertable

### Create the first administrator

There are no seed passwords in migrations. Create the first account explicitly:

```powershell
$env:ADMIN_PASSWORD = "choose-a-strong-password-at-least-12-chars"
.\.venv\Scripts\python.exe .\scripts\create_admin.py --email admin@example.com
Remove-Item Env:ADMIN_PASSWORD
```

If `ADMIN_PASSWORD` is not set, the script prompts twice without echoing.

### Run the backend API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

OpenAPI documentation: <http://127.0.0.1:8000/docs>.

Authentication endpoints:

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/login` | Email + password → access token + refresh token |
| POST | `/auth/refresh` | Rotate a refresh token (single use) |
| POST | `/auth/logout` | Revoke the current refresh token |
| GET | `/auth/me` | Current user (Bearer access token) |
| GET | `/devices` | Devices owned by the caller (admins see all) |
| GET | `/devices/{device_id}` | One device; another user's device returns 404 |
| GET | `/devices/{device_id}/channels` | Channels for an owned device |

Access tokens are HS256 JWTs valid for 15 minutes by default. Refresh tokens are
random 256-bit values stored only as SHA-256 hashes, valid for 14 days, and
rotated on every use. Reuse revokes the whole rotation family and writes an
audit entry. Login failures are rate-limited in process (5 attempts / 5 minutes
by default); this is a single-process MVP limitation, not a distributed limiter.

### Run the tests

The suite uses a throwaway `smart_panel_test` database on the same server. It
never modifies `smart_panel`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Current Test Suite Status: **79 passed, 1 warning in ~14 seconds**.
All backend algorithms, schema constraints, API endpoints, and end-to-end simulation workflows are 100% verified.

## Safety Principle

AI provides anomaly detection and analytical insights. Deterministic protection rules in firmware remain responsible for safety-critical decisions. Relays are switched only by human operator commands, operator-configured schedules, or local firmware protection.

---

## MVP Feature Status Matrix

| MVP Feature | Status | Verification Evidence / File |
|---|---|---|
| **PostgreSQL 17 + TimescaleDB 2.31** | **Built and tested in simulation** | ackend/alembic/versions/ (Migrations 0001–0005) |
| **JWT Authentication & Rate Limiting** | **Built and tested in simulation** | ackend/app/api/auth.py, ackend/app/services/auth.py |
| **Edge Modbus Glitch Filter** | **Built and tested in simulation** | ackend/app/services/mqtt_adapter.py (50–300 V, 0–50 A, PF <= 1.0) |
| **Historical CSV Data Cleaning** | **Built and tested in simulation** | data/cleaned/, docs/data_quality_report.md |
| **24-Feature Load Fingerprinting** | **Built and tested in simulation** | ackend/app/services/fingerprint.py |
| **Load Recognition Engine** | **Built and tested in simulation** | ackend/app/services/recognition.py (Weighted Euclidean distance) |
| **Declarative Mode Suggestions** | **Built and tested in simulation** | ackend/app/rules/mode_rules.yaml, ackend/app/services/mode_suggester.py |
| **Real-Time Anomaly Detection** | **Built and tested in simulation** | ackend/app/services/anomaly_detector.py (Rolling Z-scores + Inrush filter) |
| **Runtime Policy Enforcement** | **Built and tested in simulation** | ackend/app/services/mode_enforcer.py (Always-On guard, motor stall alerts) |
| **React 18 + Vite Dashboard** | **Built and tested (UI mock/dev)** | dashboard/ (Instrumentation, AIPanel, ProfilesPanel, LoginForm) |
| **Safe Telemetry Simulator** | **Built and tested in simulation** | simulator/telemetry_simulator.py |
| **Hardware Specification & Pinouts** | **Verified Baseline** | docs/hardware_notes.md |
| **Authoritative MQTT Contract** | **Verified Contract** | docs/mqtt_contract.md |
| **ESP32-S3 PlatformIO Firmware** | **Partly (Prototype in reference/)** | To be built in **Workstream 2** (FreeRTOS tasks, inrush blanking, 3-strike lockout) |
| **Proposed vs Confirmed Limits Flow**| **Partly** | To be completed in **Workstream 3** |
| **Real Remote Control & Ack Loop** | **Partly** | To be completed in **Workstream 4** (FastAPI MQTT publisher + Ack listener) |
| **Automatic Background Ingestion** | **Partly** | To be completed in **Workstream 5** (Background MQTT subscriber in FastAPI) |
| **User Registration & Device Sharing** | **Not started** | To be built in **Workstream 6** (device_members, roles) |
| **On-Device Schedules & Timers** | **Partly (Table exists)** | To be built in **Workstream 7** (Device sync + execution) |
| **Per-Load Isolation Forest on Disk** | **Partly (Class exists)** | To be built in **Workstream 8** (joblib persistence, health score 0–100) |
| **Dashboard History, Events & kWh** | **Partly (AIPanel mini-list)** | To be built in **Workstream 9** |
| **Multi-Tenant Fault Simulator** | **Partly** | To be built in **Workstream 10** |
| **Formal Hardware Bench Validation** | **Protocols Specified** | To be performed in **Workstream 11** (Protocols A–D) |
| **Production Hardening** | **Partly** | To be completed in **Workstream 12** |
