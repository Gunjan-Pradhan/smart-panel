# Architecture

**Status:** Phase 2 implemented (database, authentication, ownership).
**Last updated:** 2026-10-29

This document describes the system components, the data flow that exists today,
and the boundaries that later phases must preserve.

---

## 1. Components

| Component | Technology | Phase | Responsibility |
|---|---|---|---|
| Protection panel | ESP32-S3 + 2 × PZEM-004T V4 + 2 × SSR-40DA | 7 | Measure both channels, apply deterministic protection, publish telemetry, acknowledge commands |
| Broker | Eclipse Mosquitto 2.0.22 | 1 | MQTT transport between firmware and backend |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Alembic | 2–6 | Validate/ingest telemetry, expose REST/WebSocket APIs, enforce authorization and safety rules, issue commands |
| Database | PostgreSQL 17 + TimescaleDB 2.31 | 2–9 | Source of truth for users, devices, loads, telemetry, events, commands, schedules, audit and AI results |
| Dashboard | React + Vite | 5–6 | Live readings, history, faults, relay control and schedules |
| Simulator | Python | 3 | Contract-valid telemetry, command acknowledgements and fault injection without hardware |
| AI/ML | NumPy, Pandas, scikit-learn | 8–9 | Load fingerprints, anomaly detection and advisory health scores |

---

## 2. Current data flow (Phase 2)

```
React dashboard (Phase 5)
        │  HTTPS/JSON (planned)
        ▼
FastAPI backend ──────────────► PostgreSQL + TimescaleDB
   │  /auth/*, /devices          users, refresh_tokens, devices,
   │                             loads, channels, events, commands,
   │                             schedules, audit_log, telemetry
   │
   └── MQTT ingestion is added in Phase 4
          ▲
          │
     Mosquitto (Phase 1)
          ▲
          │
     ESP32-S3 (Phase 7)
```

Only the REST authentication and read-only device endpoints exist now. MQTT
telemetry ingestion, command publication and WebSocket push are deliberately
deferred to Phases 4 and 6.

---

## 3. Authentication flow

1. `POST /auth/login` receives email and password.
2. The backend normalizes the email, looks up the user and verifies the
   Argon2id hash. Failures return the same generic 401 message and are audited.
3. On success the backend returns:
   - a 15-minute HS256 JWT access token (`sub`, `role`, `iat`, `exp`, `jti`);
   - a 14-day opaque refresh token (256 bits).
4. Only the SHA-256 hash of the refresh token is stored. The raw value is
   returned once.
5. `POST /auth/refresh` rotates the token: the old row is marked revoked and a
   successor is inserted in the same `family_id`.
6. Replaying a consumed token revokes the whole family and writes a
   `REFRESH_TOKEN_REUSE` audit entry. The first detection is audited; later
   replays of the same dead family are rejected without flooding the log.
7. `POST /auth/logout` revokes the presented refresh token.

The access token is stateless, so deactivation is enforced by loading the user
from the database on every authenticated request (`is_active` must be true).

---

## 4. Ownership and authorization

- Every device belongs to exactly one user in the MVP.
- Non-admin queries filter by `devices.owner_id = current_user.id`.
- A request for another user's device returns **404**, not 403, so the API does
  not confirm that the device exists.
- Admin accounts may read every device. Write/control roles are defined in the
  schema (`admin`, `operator`, `viewer`) and will be enforced per endpoint as
  control APIs are added.
- The MQTT broker does not authenticate dashboard users. The backend is the
  policy enforcement point.

---

## 5. Trust boundaries and secrets

| Boundary | Current state | Deployment requirement |
|---|---|---|
| Dashboard → backend | CORS allows configured origins; HTTP locally | TLS, restrictive CORS, secure cookies or token storage |
| Backend → database | Password in `.env`, never committed | Secret manager, least-privilege database role |
| Backend → broker | Not connected yet | Authenticated MQTT, TLS, topic ACLs |
| Firmware → broker | Not connected yet | Per-device credentials, TLS, restricted topics |
| JWT signing key | `JWT_SECRET` in `.env` | ≥ 32 random characters; startup rejects missing/short/example values |

`.env` is ignored by Git. `.env.example` contains placeholders only. Migrations
contain no passwords; the first account is created with
`scripts/create_admin.py`.

---

## 6. Safety principle

AI output is advisory. Deterministic protection rules and explicit,
user-confirmed channel limits remain responsible for safety-critical decisions.
A channel with unconfirmed limits must refuse `ON` commands when the control
path is implemented in Phase 6. The dashboard must label relay state as
"commanded" because the SSR provides no feedback contact.

This is a prototype, not certified electrical protection.

---

## 7. Known gaps at the end of Phase 2

- No MQTT ingestion, WebSocket stream, command endpoint or schedule executor.
- No registration, password-reset or user-management API; use the admin CLI.
- Login rate limiting is in-process only.
- Telemetry retention/compression policies are not configured.
- No physical hardware test has been performed.
