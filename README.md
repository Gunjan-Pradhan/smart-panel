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

Expected at the end of Phase 2: **44 passed** (one Starlette/httpx deprecation
warning, recorded in `docs/testing.md`).

## Safety Principle

AI provides anomaly detection and analytical insights. Deterministic protection rules remain responsible for safety-critical decisions.

## Development Status

- **Phase 1 — complete:** Mosquitto broker, MQTT contract, health checks, persistence.
- **Phase 2 — complete:** PostgreSQL + TimescaleDB schema, SQLAlchemy models, Alembic
  migrations, Argon2id passwords, JWT access tokens, rotating refresh tokens,
  audit log, device ownership enforcement (404 for another user's device), and
  the test suite (44 passing).
- **Next:** Phase 3 — device simulator.

No physical hardware tests have been performed. The system is a prototype and
does not replace certified electrical protection.
