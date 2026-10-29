# Database Schema Design

**Status:** Implemented in migrations `0002`–`0004` and verified on 2026-10-29 (44 backend tests passing, including schema constraints and cross-user authorization). PostgreSQL 17.11 + TimescaleDB 2.31.0 run via the documented local fallback image build.
**Phase:** 2, Steps 2.1–2.4
**Date:** 2026-10-28 (design), 2026-10-29 (implementation verification)
**Target:** PostgreSQL 17 + TimescaleDB 2.31.0 (image `timescale/timescaledb:2.31.0-pg17`)

This document defines the schema that Phases 2–9 will implement. The Phase 2
tables are now implemented; Phase 9 tables (`anomaly_scores`, `health_scores`)
remain design-only.

---

## 1. Design principles

1. **PostgreSQL is the source of truth** for users, devices, loads, commands, schedules, events, telemetry and AI results.
2. **UTC everywhere.** Every timestamp column is `timestamptz`; local time exists only in schedule evaluation.
3. **Safety limits are explicit data, never inferred.** A channel cannot accept an `ON` command until its electrical limits have been entered and confirmed by an authorized user.
4. **AI output is advisory.** Anomaly and health tables are read-only inputs to the UI; they never modify channel limits or relay state.
5. **Never delete telemetry to hide a problem.** Corrections are new rows or explicit status fields.
6. **UUIDs** for user-facing entities; **bigint identity** for high-volume log rows; composite keys for time-series data.
7. **Text + CHECK constraints** instead of PostgreSQL `ENUM` types, so adding a value is a normal migration rather than an enum rewrite.
8. **Ownership is enforced in queries**, not only in the UI. Every device belongs to exactly one user in the MVP; `admin` accounts may see all devices for administration.

---

## 2. Entity relationship overview

```
users 1 ──── * devices 1 ──── * channels * ──── 0..1 loads
  │                │                                  │
  │                ├──── * telemetry (hypertable)      ├──── * load_fingerprints
  │                ├──── * events                     └──── * (assigned to channels)
  │                ├──── * commands
  │                ├──── * schedules
  │                └──── * health_scores / anomaly_scores (Phase 9)
  │
  ├──── * refresh_tokens
  └──── * audit_log
```

- A **user** owns zero or more **devices**.
- A **device** has exactly two **channels** (`ch` = 1 and 2) in this project.
- A **channel** may reference one **load** (the physical equipment currently wired to it).
- **Telemetry**, **events**, **commands**, **schedules**, **health scores** and **anomaly scores** belong to a device (and usually a channel).
- **Load fingerprints** describe a load and are independent of the channel currently using it.

---

## 3. Naming conventions

| Convention | Meaning |
|---|---|
| `*_pk` | Internal UUID primary key, used for foreign keys (e.g. `device_pk`) |
| `device_id` | Human/business identifier from the MQTT contract, e.g. `PANEL-0001` |
| `ch` | Channel number, integer 1 or 2 |
| `*_at` | Timestamp (`timestamptz`) |
| `*_v`, `*_a`, `*_w`, `*_hz` | Physical unit suffixes on numeric columns |
| Tables | Plural, `snake_case` |

Why `device_pk` and `device_id` both exist: foreign keys should not depend on a user-editable business string. Renaming a device ID later must not silently move telemetry between devices.

---

## 4. Tables

### 4.1 `users`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | Generated in application code (UUID v4) |
| `email` | text | NOT NULL, UNIQUE (`lower(email)`) | Stored lower-case |
| `password_hash` | text | NOT NULL | Argon2id encoded hash; never a plain password |
| `role` | text | NOT NULL, CHECK in (`admin`, `operator`, `viewer`) | Least privilege by default: `viewer` |
| `is_active` | boolean | NOT NULL, DEFAULT true | Disabling blocks login |
| `created_at` | timestamptz | NOT NULL, DEFAULT now() | |
| `updated_at` | timestamptz | NOT NULL, DEFAULT now() | |
| `last_login_at` | timestamptz | NULL | Updated on successful login |

**Rules**

- Emails are unique case-insensitively.
- `password_hash` must never appear in API responses or logs.
- Deleting a user is not allowed while devices reference them (`ON DELETE RESTRICT`); deactivate instead.

---

### 4.2 `refresh_tokens`

Opaque refresh tokens, stored **hashed**, rotated on every use.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `user_id` | uuid | FK → `users.id`, ON DELETE CASCADE, NOT NULL | |
| `token_hash` | char(64) | NOT NULL, UNIQUE | SHA-256 hex of the raw token |
| `family_id` | uuid | NOT NULL | Rotation family; reuse revokes the whole family |
| `issued_at` | timestamptz | NOT NULL, DEFAULT now() | |
| `expires_at` | timestamptz | NOT NULL | e.g. 14 days (configurable) |
| `revoked_at` | timestamptz | NULL | Set on logout, reuse detection or password change |
| `replaced_by_id` | uuid | FK → `refresh_tokens.id`, NULL | Rotation chain |
| `user_agent` | text | NULL | Diagnostics only, truncated |
| `ip_address` | inet | NULL | Diagnostics only |

**Rules**

- The raw refresh token is returned to the client once and never stored.
- Access tokens are stateless JWTs (short-lived); refresh tokens are stateful and revocable.
- Reuse of an already-rotated token revokes its entire `family_id` and is logged.

---

### 4.3 `devices`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `device_id` | text | NOT NULL, UNIQUE, CHECK regex `^[A-Z0-9]{2,16}-[0-9]{4}$` | e.g. `PANEL-0001` |
| `name` | text | NOT NULL | User-facing label |
| `owner_id` | uuid | FK → `users.id`, ON DELETE RESTRICT, NOT NULL | Single owner in MVP |
| `mqtt_username` | text | UNIQUE, NULL | Broker username; **no password stored here** |
| `fw_version` | text | NULL | Last reported firmware |
| `is_active` | boolean | NOT NULL, DEFAULT true | Revokes access and ignores telemetry when false |
| `online` | boolean | NOT NULL, DEFAULT false | Last known connectivity |
| `last_seen_at` | timestamptz | NULL | Updated from telemetry/status/ack |
| `last_status` | jsonb | NULL | Latest status payload (diagnostics only) |
| `created_at` | timestamptz | NOT NULL, DEFAULT now() | |
| `updated_at` | timestamptz | NOT NULL, DEFAULT now() | |

**Indexes:** `owner_id`, `last_seen_at`.

**Rules**

- MQTT credentials live in the broker password file, not in this database. Only the username is stored for correlation.
- `last_status` is a convenience cache; authoritative history lives in `events` and `telemetry`.

---

### 4.4 `channels`

One row per device channel, created with the device (2 rows).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `device_pk` | uuid | FK → `devices.id`, ON DELETE CASCADE, NOT NULL | |
| `ch` | smallint | NOT NULL, CHECK `ch IN (1,2)` | |
| `name` | text | NOT NULL | e.g. "Motor", "Bulb" |
| `load_pk` | uuid | FK → `loads.id`, ON DELETE SET NULL, NULL | Currently assigned load |
| `state` | text | NOT NULL, DEFAULT `OFF`, CHECK in §4.4.1 | Mirrors MQTT device state |
| `relay_commanded` | boolean | NOT NULL, DEFAULT false | **Commanded** state, not verified feedback |
| `last_telemetry_at` | timestamptz | NULL | Freshness / stale detection |
| `rated_voltage_v` | numeric(7,2) | NULL | Nameplate |
| `rated_current_a` | numeric(7,3) | NULL | Nameplate |
| `rated_power_w` | numeric(9,2) | NULL | Nameplate |
| `limit_voltage_min_v` | numeric(7,2) | NULL | Protection threshold |
| `limit_voltage_max_v` | numeric(7,2) | NULL | Protection threshold |
| `limit_current_a` | numeric(7,3) | NULL | Protection threshold |
| `limit_power_w` | numeric(9,2) | NULL | Protection threshold |
| `limit_freq_min_hz` | numeric(5,2) | NULL | Protection threshold |
| `limit_freq_max_hz` | numeric(5,2) | NULL | Protection threshold |
| `limit_pf_min` | numeric(4,3) | NULL | Power-factor threshold (if applicable) |
| `startup_blanking_ms` | integer | NULL, CHECK `>= 0` | Inrush blanking |
| `retry_delay_s` | integer | NOT NULL, DEFAULT 30, CHECK `> 0` | Three-strike retry timing |
| `max_retries` | smallint | NOT NULL, DEFAULT 3, CHECK `BETWEEN 1 AND 10` | Guide specifies 3 |
| `limits_confirmed_by` | uuid | FK → `users.id`, ON DELETE SET NULL, NULL | Explicit approval |
| `limits_confirmed_at` | timestamptz | NULL | **Required before any ON command is accepted** |
| `created_at` | timestamptz | NOT NULL, DEFAULT now() | |
| `updated_at` | timestamptz | NOT NULL, DEFAULT now() | |

**Constraints:** UNIQUE (`device_pk`, `ch`); CHECK for min < max where both present; all limits `> 0` where present; `startup_blanking_ms` upper bound (e.g. 60 000) to catch unit mistakes.

#### 4.4.1 Allowed channel `state` values

Same vocabulary as the MQTT contract: `OFF`, `STARTING`, `RUNNING`, `TRIPPED`, `RETRY_WAIT`, `LOCKED_OUT`, `METER_FAULT`.

Backend-only states (`UNKNOWN`, `STALE`, `OFFLINE`) are derived for display and are **not** stored here.

**Safety rules**

- `limits_confirmed_at IS NULL` ⇒ backend refuses to send `ON` and the dashboard shows "limits not configured".
- Thresholds are **entered by the user from the load nameplate**, never derived by AI.
- AI may *propose* limits for review, but the proposal is stored separately and cannot populate these columns automatically.
- `relay_commanded` must be labelled "commanded" in the UI (the SSR has no feedback contact).
- `load_pk` must reference a load owned by the same user as the device. This cannot be expressed with a simple foreign key and is therefore enforced in application code and covered by an ownership test.
- Exactly two channel rows (1 and 2) are created in the same transaction as their device; there is no database trigger for this.

---

### 4.5 `loads`

Persistent load identities such as `LP-0003`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `load_code` | text | NOT NULL, UNIQUE, regex `^LP-[0-9]{4}$` | User-visible, never reused |
| `owner_id` | uuid | FK → `users.id`, ON DELETE RESTRICT, NOT NULL | |
| `name` | text | NOT NULL | e.g. "Workshop motor" |
| `category` | text | NOT NULL, CHECK in (`motor`, `lighting`, `heater`, `other`) | Coarse class only |
| `rated_voltage_v` | numeric(7,2) | NULL | |
| `rated_current_a` | numeric(7,3) | NULL | |
| `rated_power_w` | numeric(9,2) | NULL | |
| `rated_pf` | numeric(4,3) | NULL | |
| `notes` | text | NULL | |
| `created_at` | timestamptz | NOT NULL, DEFAULT now() | |
| `updated_at` | timestamptz | NOT NULL, DEFAULT now() | |
| `archived_at` | timestamptz | NULL | Soft archive; history preserved |

**Rules**

- `load_code` is allocated by the backend (next unused number) and never reassigned.
- A load may be moved between channels over time; telemetry stores the load assigned at write time.
- Deleting a load is not offered; archive instead.

---

### 4.6 `load_fingerprints`

Learned electrical fingerprints per load (Phase 8).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `load_pk` | uuid | FK → `loads.id`, ON DELETE CASCADE, NOT NULL | |
| `feature_version` | smallint | NOT NULL | Allows feature changes without mixing profiles |
| `features` | jsonb | NOT NULL | Mean/std of active power, current, PF, inrush ratio, duty cycle, etc. |
| `sample_count` | integer | NOT NULL, CHECK `>= 1` | Evidence behind the profile |
| `confidence` | numeric(4,3) | NOT NULL, CHECK `BETWEEN 0 AND 1` | Match confidence |
| `confirmed_by` | uuid | FK → `users.id`, NULL | NULL = unverified suggestion |
| `confirmed_at` | timestamptz | NULL | |
| `is_active` | boolean | NOT NULL, DEFAULT true | Only one active profile per (load, feature_version) |
| `created_at` | timestamptz | NOT NULL, DEFAULT now() | |

**Rules**

- Low-confidence matches are stored as suggestions; the channel is not silently relabelled.
- User correction inserts a new profile/assignment and records an audit entry.

---

### 4.7 `telemetry` (TimescaleDB hypertable)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `device_pk` | uuid | FK → `devices.id`, NOT NULL | |
| `ch` | smallint | NOT NULL, CHECK `IN (1,2)` | |
| `ts` | timestamptz | NOT NULL | Device measurement time (UTC) |
| `boot_id` | text | NULL | Optional, from MQTT |
| `seq` | bigint | NULL | Optional, from MQTT |
| `v` | numeric(7,2) | NOT NULL | Volts |
| `i` | numeric(7,3) | NOT NULL | Amperes |
| `p` | numeric(9,2) | NOT NULL | Watts |
| `e_kwh` | numeric(12,3) | NOT NULL | Cumulative meter energy |
| `pf` | numeric(4,3) | NOT NULL | 0–1 |
| `f` | numeric(5,2) | NOT NULL | Hz |
| `relay` | boolean | NOT NULL | Commanded state at publish |
| `state` | text | NOT NULL | Device state enum |
| `buffered` | boolean | NOT NULL | Replayed from offline buffer |
| `clock_synced` | boolean | NULL | Device clock confidence |
| `load_pk` | uuid | FK → `loads.id`, NULL | Load assigned when stored |
| `received_at` | timestamptz | NOT NULL, DEFAULT now() | Backend receipt time |

**Primary key:** (`device_pk`, `ch`, `ts`) — includes the partitioning column, as TimescaleDB requires.

**Indexes:** (`device_pk`, `ch`, `ts DESC`); optional `received_at` for ingestion diagnostics.

**Why no unique `(boot_id, seq)`:** TimescaleDB requires unique indexes to include the time column, so it cannot enforce that pair globally. Duplicate uploads are therefore rejected in the ingestion layer **before** insert, and the primary key catches exact timestamp duplicates as a second line of defence.

**Volume estimate:** 2 channels × 1 message/s = 172 800 rows/day ≈ 5.2 million rows/month. A 90-day retention window is ≈ 15.5 million rows. This is comfortable for a laptop but requires a retention policy.

**Retention/compression:** policy values are configuration, not schema. The exact TimescaleDB compression/columnstore syntax will be verified against the pinned image before it is added in a later migration. The MVP can run without compression.

---

### 4.8 `events`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | Device `event_id`; duplicate delivery is idempotent |
| `device_pk` | uuid | FK → `devices.id`, ON DELETE CASCADE, NOT NULL | |
| `ch` | smallint | NULL, CHECK `ch IN (1,2)` when not null | NULL = device-level |
| `ts` | timestamptz | NOT NULL | Device event time |
| `type` | text | NOT NULL | Event enum from `docs/mqtt_contract.md` |
| `severity` | text | NOT NULL, CHECK in (`info`,`warning`,`critical`) | |
| `message` | text | NOT NULL, max 200 chars (app validation) | |
| `data` | jsonb | NULL | Rule, measured value, threshold, `cmd_id`, etc. |
| `received_at` | timestamptz | NOT NULL, DEFAULT now() | |

**Indexes:** (`device_pk`, `ts DESC`), (`type`), (`severity`).

**Rules**

- Event types are validated against the MQTT contract before insert.
- A duplicate `event_id` is ignored, not inserted twice.
- Commands rejected by the device must also create a `CMD_REJECTED` event (contract §7.1).

---

### 4.9 `commands`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `cmd_id` | uuid | PK | From the MQTT contract |
| `device_pk` | uuid | FK → `devices.id`, ON DELETE CASCADE, NOT NULL | |
| `ch` | smallint | NOT NULL, CHECK `IN (1,2)` | |
| `action` | text | NOT NULL, CHECK in (`ON`,`OFF`) | |
| `source` | text | NOT NULL, CHECK in (`user`,`schedule`,`system`,`optimization`) | |
| `requested_by` | uuid | FK → `users.id`, ON DELETE SET NULL, NULL | NULL for schedule/system/AI |
| `status` | text | NOT NULL, DEFAULT `PENDING`, CHECK in (`PENDING`,`DONE`,`REJECTED`,`FAILED`,`TIMED_OUT`) | |
| `reason` | text | NULL | Acknowledgement reason code |
| `issued_at` | timestamptz | NOT NULL, DEFAULT now() | Publication time |
| `expires_at` | timestamptz | NOT NULL | Must be > `issued_at` |
| `acked_at` | timestamptz | NULL | Device acknowledgement time |
| `relay_after` | boolean | NULL | Commanded state after processing |
| `state_after` | text | NULL | Channel state after processing |
| `created_at` | timestamptz | NOT NULL, DEFAULT now() | |

**Indexes:** (`device_pk`, `issued_at DESC`), partial index on `status` where `status = 'PENDING'`.

**Invariants (application-enforced)**

- `PENDING` ⇒ `acked_at IS NULL`.
- A late acknowledgement may update `TIMED_OUT` → `DONE`/`REJECTED`/`FAILED`, with an audit note. The first received result wins; duplicate acks are ignored.
- `ON` is never persisted as `DONE` on the basis of the request alone; only a device acknowledgement or confirming telemetry may do that.

---

### 4.10 `schedules`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `owner_id` | uuid | FK → `users.id`, ON DELETE CASCADE, NOT NULL | |
| `device_pk` | uuid | FK → `devices.id`, ON DELETE CASCADE, NOT NULL | |
| `ch` | smallint | NOT NULL, CHECK `IN (1,2)` | |
| `name` | text | NOT NULL | |
| `days_of_week` | smallint | NOT NULL, CHECK `BETWEEN 1 AND 127` | Bitmask: Mon=1, Tue=2, … Sun=64 |
| `on_time` | time | NOT NULL | Local time in `timezone` |
| `off_time` | time | NOT NULL | Must differ from `on_time` |
| `timezone` | text | NOT NULL | IANA name, e.g. `Asia/Kolkata`; validated by the app |
| `enabled` | boolean | NOT NULL, DEFAULT true | |
| `created_at` | timestamptz | NOT NULL, DEFAULT now() | |
| `updated_at` | timestamptz | NOT NULL, DEFAULT now() | |

**Rules**

- Application-level validation rejects overlapping enabled schedules on the same channel; the database cannot express that cleanly with weekday bitmasks and overnight windows.
- `OFF` windows are fail-safe: a schedule may not hold a channel on after a protection trip or lockout.
- **Offline requirement:** schedules must eventually execute on the device, not only in the backend. That needs a contract extension (the reserved schedule topic) and is tracked as an open item in §9.

---

### 4.11 `audit_log`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | bigint | PK, identity | High volume |
| `ts` | timestamptz | NOT NULL, DEFAULT now() | |
| `user_id` | uuid | FK → `users.id`, ON DELETE SET NULL, NULL | NULL for system actions |
| `action` | text | NOT NULL | e.g. `LOGIN`, `COMMAND_SENT`, `LOCKOUT_RESET`, `LIMITS_CONFIRMED` |
| `entity_type` | text | NOT NULL | e.g. `device`, `channel`, `schedule` |
| `entity_id` | text | NULL | String to allow non-UUID identifiers |
| `detail` | jsonb | NULL | Before/after values (never secrets) |
| `ip_address` | inet | NULL | |

**Indexes:** (`ts DESC`), (`user_id`, `ts DESC`).

Manual lockout resets, threshold confirmations, schedule changes and command rejections must be auditable.

---

### 4.12 `anomaly_scores` (Phase 9 — not in the initial migration)

| Column | Type | Constraints |
|---|---|---|
| `id` | bigint | PK, identity |
| `device_pk` | uuid | FK → `devices.id`, ON DELETE CASCADE, NOT NULL |
| `ch` | smallint | NOT NULL, CHECK `IN (1,2)` |
| `ts` | timestamptz | NOT NULL |
| `model_name` | text | NOT NULL, e.g. `isolation_forest` |
| `model_version` | text | NOT NULL |
| `score` | numeric(10,6) | NOT NULL |
| `is_anomaly` | boolean | NOT NULL |
| `severity` | text | CHECK in (`info`,`warning`,`critical`) |
| `explanation` | jsonb | NULL (feature contributions / context) |
| `created_at` | timestamptz | NOT NULL, DEFAULT now() |

**Index:** (`device_pk`, `ch`, `ts DESC`).

### 4.13 `health_scores` (Phase 9 — not in the initial migration)

| Column | Type | Constraints |
|---|---|---|
| `id` | bigint | PK, identity |
| `device_pk` | uuid | FK → `devices.id`, ON DELETE CASCADE, NOT NULL |
| `ch` | smallint | NOT NULL, CHECK `IN (1,2)` |
| `ts` | timestamptz | NOT NULL |
| `score` | numeric(5,2) | NOT NULL, CHECK `BETWEEN 0 AND 100` |
| `components` | jsonb | NOT NULL (per-indicator contributions) |
| `confidence` | numeric(4,3) | CHECK `BETWEEN 0 AND 1` |
| `created_at` | timestamptz | NOT NULL, DEFAULT now() |

Health scores are advisory and must never be described as remaining-life prediction.

---

## 5. Access and ownership rules

| Role | Devices | Telemetry/history | Commands | Schedules | Limits | Users |
|---|---|---|---|---|---|---|
| `viewer` | own only (read) | own only | no | no | read | self |
| `operator` | own only | own only | ON/OFF + reset within safety | own | read | self |
| `admin` | all | all | all | all | all | manage |

Enforcement requirements:

- Every repository/query for a non-admin filters by `devices.owner_id = current_user.id`.
- A request for another user's device returns **404**, not 403, to avoid confirming existence.
- Backend tests must prove cross-user access fails for devices, channels, telemetry, events, commands and schedules.
- The MQTT broker does not perform user authorization; the backend is the policy enforcement point.

---

## 6. Authentication design (summary)

- Passwords: **Argon2id** via `argon2-cffi`, stored as the encoded hash string.
- Access token: JWT (HS256), 15-minute lifetime, claims `sub` (user id), `role`, `iat`, `exp`, `jti`.
- Refresh token: 256-bit random, SHA-256 hashed in `refresh_tokens`, 14-day lifetime, rotated on every refresh.
- Logout revokes the current refresh token; reuse of a rotated token revokes the family and writes an audit entry.
- Secret key comes from `JWT_SECRET`; application startup fails if it is missing, too short (< 32 chars) or still the example value outside development.
- Login failures return a generic message and are rate-limited (simple in-memory limiter for MVP; document the single-process limitation).
- CORS allows only the configured dashboard origin(s).

---

## 7. Migration plan

The numbering below is the implemented order. Authentication tables were split
from the rest of the core tables so each migration could be reviewed and tested
on its own.

1. **Migration 0001 — extensions (implemented):** enable `timescaledb`. `pgcrypto` is intentionally not enabled; UUIDs are generated in Python.
2. **Migration 0002 — authentication tables (implemented):** `users`, `refresh_tokens`.
3. **Migration 0003 — core tables (implemented):** `devices`, `loads`, `channels`, `events`, `commands`, `schedules`, `audit_log`.
4. **Migration 0004 — telemetry hypertable (implemented):** create `telemetry`, run `create_hypertable('telemetry','ts')`, then create indexes.
5. **Migration 0005 — policies (later):** retention (and compression if verified). Separate migration so the MVP can deploy without policy assumptions.
6. **Migration 0006 (Phase 9):** `anomaly_scores`, `health_scores`.

Rules:

- Every migration has a working `downgrade()`.
- No seed passwords in migrations. The first admin is created by `scripts/create_admin.py`, which reads the password from `ADMIN_PASSWORD` or a hidden prompt.
- `alembic upgrade head` must work on an empty database and be idempotent from a previous revision.
- Schema changes are never applied by `Base.metadata.create_all()` in production paths; Alembic owns the schema.
- CheckConstraint names in migrations use the **short** form (for example `name="ch_allowed"`). The naming convention in `app/db/base.py` adds the `ck_<table>_` prefix once. Passing a full name would produce `ck_channels_ck_channels_...`.

---

## 8. Testing plan for Phase 2

| Test | Expected |
|---|---|
| `alembic upgrade head` on empty DB | exit 0; all tables exist |
| `alembic downgrade base` | exit 0; tables removed |
| Re-apply migrations | exit 0 |
| Insert `ch = 3` | rejected by CHECK |
| Insert duplicate telemetry `(device_pk, ch, ts)` | rejected by PK |
| Insert telemetry with non-existent `device_pk` | rejected by FK |
| Health score `101` | rejected by CHECK |
| User A reads user B's device | 404 |
| User A sends command to user B's device | 404, no command row |
| Refresh-token reuse | family revoked; audit entry written |
| Login with wrong password | 401, no token, audit entry |
| Deactivate user | existing refresh tokens rejected |

---

## 9. Open questions (need your decision before implementation)

1. **PostgreSQL major version:** proposal is **17** (mature, well documented). TimescaleDB also publishes pg18 images. Confirm 17 or request 18.
2. **Default schedule timezone:** I do not want to assume your location. Proposal: no hard-coded default; the user selects an IANA timezone when creating a schedule. The Docker container runs UTC.
3. **Telemetry retention:** proposal **90 days** locally, configurable. Confirm or choose another period.
4. **Multi-user device sharing:** out of scope for the MVP (single owner + admin). Confirm.
5. **Hardware ratings:** channel limits stay `NULL`/unconfirmed until you supply nameplate data. This intentionally blocks `ON` commands in early tests; the simulator can use test-only limits marked as such.
6. **Offline schedules:** local device execution requires a contract extension. Confirm that Phase 6 implements backend scheduling first and Phase 7 adds device-side execution, rather than claiming offline schedules early.

---

## 10. Change history

| Date | Change |
|---|---|
| 2026-10-28 | Initial schema proposal (Phase 2, Step 2.1) |
| 2026-10-29 | Implemented migrations 0002–0004; added SQLAlchemy models; corrected doubled CheckConstraint names in 0002; documented the short-name rule |
| 2026-10-29 | Verified hypertable, constraints, cascade behaviour and downgrade/upgrade cycle with 44 passing backend tests |
