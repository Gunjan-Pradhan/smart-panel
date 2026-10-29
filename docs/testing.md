# Testing Guide and Results

**Project:** AI-Based Smart Load Protection Panel
**Document status:** Living document. Updated at the end of every tested step.
**Last updated:** 2026-10-29
**Current phase:** Phase 2 complete — schema, migrations, authentication, ownership enforcement and 44 passing backend tests. Phase 3 (device simulator) is next.

---

## 1. Purpose

This document records **what was tested, how to reproduce it, and what the observed result was**. It exists so that:

- you can re-run every check yourself,
- a marker/examiner can distinguish verified behaviour from claims,
- future tests can be compared against earlier results,
- simulated tests are never presented as physical hardware tests.

Reading rule:

- **Expected** = what the test should produce.
- **Observed** = what actually happened, copied from the terminal.
- A test is only "passed" if it was executed and matched the expected result.
- A test listed as "not run" is not a passed test.

---

## 2. Evidence rules

1. Every test needs a command, an expected result and an observed result.
2. Never widen validation or disable a safety check to make a test pass. Fix the defect instead.
3. Mark the environment: `simulated`, `container`, `host software`, or `physical hardware`.
4. **No physical hardware test may be claimed until it has been performed with proper supervision.** At the time of writing, **no hardware tests have been performed**.
5. Screenshots are supporting evidence, not a replacement for commands and exit codes.
6. When a test fails, record the failure and the diagnosis; do not delete it from history.

---

## 3. Verified environment (2026-10-28)

| Component | Version / value | How verified |
|---|---|---|
| Operating system | Windows (host) | Environment |
| Python (project venv) | 3.13.2 | `python --version` |
| pip | 26.2.2 | `python -m pip --version` |
| Docker CLI | 29.9.2 | `docker --version` |
| Docker Compose | v5.6.1 | `docker compose version` |
| Docker engine | 29.9.2, Linux containers | `docker info` |
| Mosquitto image | `eclipse-mosquitto:2.0.22` | Pulled by Compose |
| Database image | `smart-panel/timescaledb:2.31.0-pg17` (local fallback build: ECR PostgreSQL 17.11 + TimescaleDB 2.31.0 apt package) | `docker compose build db` |
| Broker endpoint (development) | `127.0.0.1:1883` | Compose port mapping |
| Broker authentication | Anonymous, loopback only | `mosquitto/config/mosquitto.conf` |
| Node.js / npm | 25.2.1 / 11.21.1 | `node --version`, `npm --version` |

**Prerequisite discovered during testing:** `restart: unless-stopped` restarts a container only while the Docker engine is running. If Docker Desktop is closed (for example after a reboot), the broker stays down. Start Docker Desktop before running any infrastructure test.

---

## 4. How to run the Phase 1 tests

Run from the project root in PowerShell:

```powershell
cd C:\Users\gunjan\OneDrive\Desktop\FINAL_PROJECT\smart-panel

# 0. Docker Desktop must be running
docker info --format '{{.ServerVersion}} {{.OSType}}'

# 1. Validate the Compose file
docker compose config --quiet

# 2. Start the broker
docker compose up -d mosquitto

# 3. Confirm the container is healthy
docker compose ps

# 4. Run the automated MQTT round trip
.\.venv\Scripts\python.exe .\scripts\mqtt_smoke_test.py
echo $LASTEXITCODE
```

Expected exit code for steps 1, 2 and 4: `0`.
Expected container status: `Up ... (healthy)` with port `127.0.0.1:1883->1883/tcp`.

Stop the broker when finished (keeps the data volume):

```powershell
docker compose down
```

---

## 5. Phase 1 test cases

All tests below are **infrastructure/software tests**. None involve mains voltage or the ESP32.

### T-INF-001 — Compose configuration is valid

| Item | Detail |
|---|---|
| Type | Host software / static |
| Command | `docker compose config --quiet` |
| Expected | Exit code `0`, no output |
| Observed (2026-10-28) | Exit code `0`, no output |
| Status | **PASS** |

Why it matters: catches YAML errors, invalid keys and malformed service definitions before starting anything.

---

### T-INF-002 — Broker container starts and reports healthy

| Item | Detail |
|---|---|
| Type | Container |
| Command | `docker compose up -d mosquitto; docker compose ps` |
| Expected | Container `smart-panel-mosquitto`, status contains `(healthy)` |
| Observed (2026-10-28) | `Up 6 seconds (healthy)`, `127.0.0.1:1883->1883/tcp` |
| Status | **PASS** |

The healthcheck runs `mosquitto_pub` inside the container, so "healthy" means the broker accepted a real client publish, not merely that a process is alive.

---

### T-INF-003 — Test script is syntactically valid

| Item | Detail |
|---|---|
| Type | Host software / static |
| Command | `.\.venv\Scripts\python.exe -m py_compile .\scripts\mqtt_smoke_test.py` |
| Expected | Exit code `0` |
| Observed (2026-10-28) | Exit code `0` |
| Status | **PASS** |

---

### T-INF-004 — Publish/subscribe round trip (QoS 1)

| Item | Detail |
|---|---|
| Type | Host software ↔ container |
| Command | `.\.venv\Scripts\python.exe .\scripts\mqtt_smoke_test.py` |
| Expected | Two `PASS` lines; exit code `0` |
| Observed (2026-10-28) | `PASS: connected to 127.0.0.1:1883` / `PASS: QoS 1 round trip on panel/_smoke/6e17f269...` ; exit `0` |
| Status | **PASS** |

What it proves: the broker accepts an external client on the loopback binding, a subscription is registered, a QoS 1 publish is delivered back byte-for-byte, and the client disconnects cleanly.

What it does **not** prove: application schema validation, command handling, or that the ESP32 can connect (it cannot in this configuration — see limitations).

---

### T-INF-005 — Retained status message is delivered to a late subscriber

| Item | Detail |
|---|---|
| Type | Container |
| Commands | See block below |
| Expected | The retained payload is returned immediately by `mosquitto_sub -C 1` |
| Observed (2026-10-28) | `{schema:1,ts:1,online:true,device_id:"PANEL-0001",fw:"persist-test"}` |
| Status | **PASS** |

```powershell
docker exec smart-panel-mosquitto mosquitto_pub -h 127.0.0.1 `
  -t 'panel/PANEL-0001/status' -r `
  -m '{"schema":1,"ts":1,"online":true,"device_id":"PANEL-0001","fw":"persist-test"}'

docker exec smart-panel-mosquitto mosquitto_sub -h 127.0.0.1 `
  -t 'panel/PANEL-0001/status' -C 1 -W 5
```

The payload is a deliberate test fixture (`ts:1`, `fw:"persist-test"`), not real device data. It is cleared after the test.

---

### T-INF-006 — Retained data survives a broker restart

| Item | Detail |
|---|---|
| Type | Container + Docker volume |
| Commands | Publish retained (T-INF-005) → `docker compose restart mosquitto` → subscribe again |
| Expected | After restart the broker is `healthy` and the retained payload is still available |
| Observed (2026-10-28) | Health `healthy`; retained payload identical to T-INF-005 |
| Status | **PASS** |

What it proves: the named volume `smart-panel-mosquitto-data` is wired correctly and Mosquitto persistence is enabled. It does **not** prove database persistence (no database exists yet).

Cleanup after the test (removes the retained fixture):

```powershell
docker exec smart-panel-mosquitto mosquitto_pub -h 127.0.0.1 `
  -t 'panel/PANEL-0001/status' -r -n
```

---

### T-INF-007 — Build and secret files are ignored by Git

| Item | Detail |
|---|---|
| Type | Repository hygiene |
| Commands | `git check-ignore -v firmware/.pio/build/firmware.bin` and the same for `.env` and `mosquitto/data/mosquitto.db` |
| Expected | Each path matches a `.gitignore` rule |
| Observed (2026-10-28) | `.pio/`, `.env`, `mosquitto/data/` matched |
| Status | **PASS** |

---

### T-INF-008 — All JSON examples in the MQTT contract are valid JSON

| Item | Detail |
|---|---|
| Type | Documentation / static |
| Command | Python script extracts every fenced JSON block and runs `json.loads` |
| Expected | Every block parses; count is reported |
| Observed (2026-10-28) | `blocks= 12 all_valid= True` |
| Status | **PASS** |

Why it matters: a contract with malformed example payloads causes copy-paste bugs in the simulator, firmware and tests.

---

### T-INF-009 — No credentials committed in the Phase 1 files

| Item | Detail |
|---|---|
| Type | Security / static |
| Command | Pattern scan of changed files for `password`, `secret`, `token` assignments |
| Expected | No real credentials; only placeholders or random test values |
| Observed (2026-10-28) | Only `token = uuid.uuid4().hex` inside the smoke-test script (random, not a secret) |
| Status | **PASS** (limited scan, not a substitute for full secret scanning) |

---

### T-INF-010 — Full stop/start cycle works as documented

| Item | Detail |
|---|---|
| Type | Container + Docker volume |
| Commands | `docker compose down` → `docker compose up -d mosquitto` → smoke test |
| Expected | Container removed then recreated, status `healthy`, smoke test exit `0`, data volume still present |
| Observed (2026-10-28) | Container created/started; `health=healthy`; smoke test exit `0`; volume `smart-panel-mosquitto-data` listed |
| Status | **PASS** |

What it proves: the documented start/stop instructions work from a clean container state and do not delete the persistence volume.

---

### T-MAN-001 — Manual inspection with MQTT Explorer (NOT RUN)

| Item | Detail |
|---|---|
| Type | Manual / visual |
| Steps | Connect MQTT Explorer to `127.0.0.1:1883`, publish a retained message to `panel/PANEL-0001/status`, disconnect, reconnect, confirm it is still there |
| Expected | Topic appears; retained message is shown after reconnect |
| Observed | **Not executed** |
| Status | **NOT RUN — optional visual confirmation** |

This is optional because T-INF-005 and T-INF-006 already verify the same behaviour programmatically.

---

## 5.1 Phase 2 dependency checks (2026-10-28)

### T-DEP-001 — Installed dependency set is internally consistent

| Item | Detail |
|---|---|
| Type | Host software |
| Command | `.\.venv\Scripts\python.exe -m pip check` |
| Expected | `No broken requirements found.` |
| Observed | `No broken requirements found.` |
| Status | **PASS** |

### T-DEP-002 — New libraries perform their core functions

| Item | Detail |
|---|---|
| Type | Host software / functional smoke test |
| Checks | Argon2id hash + verify; JWT HS256 encode/decode; `postgresql+psycopg` dialect loads; `pydantic-settings` instantiation; email validation; FastAPI `TestClient` request |
| Expected | All checks pass; installed versions match the proposal |
| Observed | All passed; versions: SQLAlchemy 2.1.6, Alembic 1.20.1, psycopg 3.3.6, PyJWT 2.15.1, pytest 9.2.0, httpx 0.28.1 |
| Status | **PASS** |

The password used in the hash test was an in-memory dummy value and was not stored.

### T-DEP-003 — No existing package version changed

| Item | Detail |
|---|---|
| Type | Host software / regression |
| Method | Compare `pip freeze` before install with the current environment, excluding newly added packages |
| Expected | No version changes to the existing FastAPI/ML/MQTT stack |
| Observed | `pre-existing packages changed: NONE` |
| Status | **PASS** |

### T-DEP-004 — Starlette warns about `httpx` vs `httpx2`

| Item | Detail |
|---|---|
| Type | Host software / compatibility warning |
| Observed | `StarletteDeprecationWarning: Using 'httpx' with 'starlette.testclient' is deprecated; install 'httpx2' instead.` |
| Impact | Tests still run. Not a failure in this step. |
| Decision | Recorded in `docs/dependencies.md` §10. `httpx2` was **not** installed because it was outside the approved list. Decide before Phase 4 API tests. |
| Status | **WARNING — open decision** |

### T-DB-001 — TimescaleDB image and container (via documented local fallback)

| Item | Detail |
|---|---|
| Type | Container / infrastructure |
| Command | `docker compose build db` then `docker compose up -d db` |
| Expected | Container `smart-panel-db` healthy; PostgreSQL 17 + TimescaleDB 2.31.0 available |
| Observed (2026-10-28) | **PASS via local build.** Official Docker Hub image could not be pulled (see blocker below), so a documented fallback image was built from AWS ECR's official PostgreSQL mirror + the official TimescaleDB apt repository. |
| Status | **PASS (fallback)** — official upstream image remains unverified |

#### Blocker discovered first (unchanged fact)

Docker Hub's blob CDN `production.cloudfront.docker.com` resets TLS on this network. Six pull attempts failed with `net/http: TLS handshake timeout`, including the control image `postgres:17-alpine`.

| Check | Result |
|---|---|
| `production.cloudfront.docker.com` | TLS reset (`curl 35`) |
| CloudFront distribution hostname (`d3ipk8a4rcghwr.cloudfront.net`) | HTTP 403 — TLS handshake succeeds |
| `https://registry-1.docker.io/v2/` | HTTP 401 — reachable |
| pypi.org / github.com | HTTP 200 |
| Clock / proxy | correct / none configured |
| `public.ecr.aws` pull test | **SUCCESS** (amd64) |
| packagecloud.io / apt.postgresql.org | HTTP 200 / 302 — reachable |

#### Fallback implementation

- `db/Dockerfile` builds on `public.ecr.aws/docker/library/postgres:17.11-bookworm`.
- Installs exact package `timescaledb-2-postgresql-17=2.31.0~debian12-1711`.
- Sets `shared_preload_libraries = 'timescaledb'`.
- Creates the extension on first database initialisation.
- `docker-compose.yml` uses `build: ./db` and tags the result `smart-panel/timescaledb:2.31.0-pg17`.
- Switching back to the official image is documented in the Dockerfile and Compose comments.

#### Observed results

| Query | Result |
|---|---|
| `SELECT version()` | PostgreSQL 17.11 (Debian 17.11-1.pgdg12+2), x86_64 |
| `extversion` | **2.31.0** |
| `SHOW shared_preload_libraries` | `timescaledb` |
| Container health | `healthy` |

**Honest limitation:** this verifies the *fallback* image, not the official `timescale/timescaledb:2.31.0-pg17` image. When Docker Hub access is restored, rebuild with the official image and repeat these tests.

### T-DB-002 — Hypertable, restart, container recreation and host authentication

| Step | Command | Expected | Observed | Status |
|---|---|---|---|---|
| Create hypertable | `create_hypertable('telemetry_test','ts')` | Returns hypertable id | `(1,public,telemetry_test,t)` | PASS |
| Insert + count | `INSERT …; SELECT count(*)` | 1 row | 1 | PASS |
| Restart container | `docker compose restart db` | Healthy; row still present | Healthy; 1 row | PASS |
| Remove + recreate container | `docker compose rm -sf db; docker compose up -d db` | Volume persists; row still present | Healthy; 1 row | PASS |
| Host connection with psycopg | Read `.env`, connect to `127.0.0.1:5432` | Authentication succeeds | PostgreSQL 17.11; Timescale 2.31.0 | PASS |
| Host write/read | Insert via psycopg | Insert and count succeed | 2 rows | PASS |
| Cleanup | `DROP TABLE telemetry_test` | Table removed | Dropped | PASS |

The temporary `telemetry_test` table was dropped after testing; no test data remains.

---

## 5.2 Phase 2 database schema and migrations (2026-10-29)

### T-DB-003 — Migration chain reaches head and is reversible

| Item | Detail |
|---|---|
| Type | Container + host integration |
| Command | `cd backend` then `..\.venv\Scripts\alembic.exe upgrade head`, `..\.venv\Scripts\alembic.exe current` |
| Expected | Revisions `0001` → `0004` apply without error; `current` reports `0004 (head)` |
| Observed | All four revisions applied; `0004 (head)`; the slow test `upgrade → downgrade base → upgrade` also passed on an isolated database |
| Status | **PASS** |

### T-DB-004 — Schema constraints reject invalid data (16 tests)

| Item | Detail |
|---|---|
| Type | Integration (PostgreSQL) |
| Command | `.\.venv\Scripts\python.exe -m pytest backend/tests/test_core_schema.py -v` |
| Checks | device ID regex; duplicate device ID; `ch = 3`; duplicate `(device_pk, ch)`; voltage min ≥ max; load code/category; `pf > 1`; duplicate telemetry primary key; telemetry FK to a missing device; event severity; command `PENDING` with an acknowledgement; command expiry; schedule weekday mask; equal schedule times; device-delete cascade; user-delete restriction; audit identity |
| Expected | Every invalid insert raises `IntegrityError`; valid rows are accepted |
| Observed | `16 passed` |
| Status | **PASS** |

### T-DB-005 — Telemetry is a TimescaleDB hypertable

| Item | Detail |
|---|---|
| Type | Container |
| Command | `docker compose exec db psql -U smart_panel_user -d smart_panel -c "SELECT hypertable_name FROM timescaledb_information.hypertables;"` |
| Expected | `telemetry` listed |
| Observed | `telemetry` listed; primary key includes `(device_pk, ch, ts)` |
| Status | **PASS** |

### T-DB-006 — Schema and data survive a container restart

| Item | Detail |
|---|---|
| Type | Container persistence |
| Steps | Insert a temporary user; `docker compose restart db`; wait for `healthy`; query the row; delete it |
| Expected | Row is still present after restart |
| Observed | `persist@example.com` returned after restart; cleanup deleted 1 row |
| Status | **PASS** |

### T-DB-007 — Windows hostname resolution defect (found and fixed)

| Item | Detail |
|---|---|
| Type | Defect / diagnosis |
| Symptom | The migration test hung at `psycopg.connect`; `faulthandler` showed the process waiting in `select()` during the connection handshake |
| Diagnosis | `getaddrinfo("localhost")` returned `::1` first. Docker publishes the port on IPv4 only, so the IPv6 attempt stalled until the OS timeout. SQLAlchemy had no `connect_timeout`. |
| Fix | `DATABASE_HOST=127.0.0.1`; `connect_timeout=10` in the Alembic engine and the application engine |
| Verification | Direct connections dropped from ~5 s (with timeout) to ~0.02 s; the full suite finished in ~14 s |
| Status | **PASS after fix** — recorded so the failure is not hidden |

---

## 5.3 Phase 2 authentication and authorization (2026-10-29)

All tests use the real PostgreSQL test database through FastAPI `TestClient`.
Passwords in the tests are in-memory values; no test credential is committed.

### T-AUTH-001 — Login, access token and `/auth/me`

| Item | Detail |
|---|---|
| Type | Integration (API + database) |
| Command | `.\.venv\Scripts\python.exe -m pytest backend/tests/test_auth_api.py -v` |
| Expected | Valid login returns `access_token`, `refresh_token`, `token_type=bearer`, `expires_in=900`; `/auth/me` returns the user and no password field |
| Observed | All assertions passed |
| Status | **PASS** |

### T-AUTH-002 — Refresh rotation and reuse detection

| Item | Detail |
|---|---|
| Type | Integration (API + database) |
| Steps | Login; refresh once (new token); replay the consumed token; try the successor |
| Expected | First refresh succeeds; replay returns 401; successor is revoked; one `REFRESH_TOKEN_REUSE` audit row |
| Observed | 200 → 401 → 401; exactly one reuse audit entry |
| Status | **PASS** |

### T-AUTH-003 — Logout revokes the refresh token

| Item | Detail |
|---|---|
| Type | Integration |
| Steps | Login; `POST /auth/logout`; try to refresh |
| Expected | Logout returns 204; refresh returns 401 |
| Observed | 204 then 401 |
| Status | **PASS** |

### T-AUTH-004 — Wrong password and unknown email

| Item | Detail |
|---|---|
| Type | Integration |
| Expected | Both return the same generic 401 message; failed login is audited; the password is never logged |
| Observed | Both returned `Invalid email or password`; one `LOGIN_FAILED` audit row |
| Status | **PASS** |

### T-AUTH-005 — Cross-user device isolation

| Item | Detail |
|---|---|
| Type | Integration |
| Steps | User A lists devices; User A requests User B's device and channels |
| Expected | Listing contains only A's device; foreign device and channels return **404** (not 403) |
| Observed | `PANEL-0001` only; both foreign requests returned 404 |
| Status | **PASS** |

### T-AUTH-006 — Admin visibility

| Item | Detail |
|---|---|
| Type | Integration |
| Steps | Admin lists devices and reads another user's device |
| Expected | Both devices visible; detail includes both channels |
| Observed | `PANEL-0001` and `PANEL-0002`; detail contained 2 channels |
| Status | **PASS** |

### T-AUTH-007 — Deactivated user and rate limiting

| Item | Detail |
|---|---|
| Type | Integration |
| Steps | Login, deactivate the user, reuse the access token; separately, fail login 5 times and try a 6th |
| Expected | Access token rejected with 401 after deactivation; 6th login returns 429 with `Retry-After` |
| Observed | 401; 429 with `Retry-After: 300` |
| Status | **PASS** |

### T-API-001 — Real Uvicorn smoke test

| Item | Detail |
|---|---|
| Type | Host software / real server |
| Command | `python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000` then HTTP requests |
| Expected | `/health` returns `{"status":"ok","phase":"2"}`; login returns a token; `/auth/me` returns the account; `/devices` returns an empty list for a new admin |
| Observed | Health 200; login `bearer`, `expires_in=900`; `/auth/me` returned the test account; `/devices` count 0; temporary account and audit rows deleted afterwards |
| Status | **PASS** |

---

## 6. Summary of the latest execution

| Test | Result |
|---|---|
| T-INF-001 Compose config | PASS |
| T-INF-002 Broker health | PASS |
| T-INF-003 Script syntax | PASS |
| T-INF-004 QoS 1 round trip | PASS |
| T-INF-005 Retained delivery | PASS |
| T-INF-006 Persistence across restart | PASS |
| T-INF-007 Ignore rules | PASS |
| T-INF-008 Contract JSON validity | PASS |
| T-INF-009 Credential scan | PASS |
| T-INF-010 Full down/up cycle | PASS |
| T-DEP-001 Dependency consistency (`pip check`) | PASS |
| T-DEP-002 New libraries functional checks | PASS |
| T-DEP-003 Existing packages unchanged | PASS |
| T-DEP-004 `httpx`/`httpx2` deprecation warning | WARNING — open decision |
| T-DB-001 TimescaleDB image/container | PASS via local fallback build |
| T-DB-002 Hypertable, restart, recreation, host auth | PASS |
| T-DB-003 Migration chain reaches `0004` and is reversible | PASS |
| T-DB-004 Schema constraint suite (16 tests) | PASS |
| T-DB-005 Telemetry hypertable | PASS |
| T-DB-006 Database persistence across restart | PASS |
| T-DB-007 Windows hostname resolution defect | PASS after fix |
| T-AUTH-001…007 Authentication and ownership (10 tests) | PASS |
| T-API-001 Real Uvicorn smoke test | PASS |
| Full backend suite (`pytest -q`) | **44 passed**, 1 warning |
| T-MAN-001 MQTT Explorer | NOT RUN (optional) |
| Physical hardware tests | **NONE PERFORMED** |

Test run date: **2026-10-29**. Initial Phase 1 run: 2026-10-27.

---

## 7. Known limitations of the current test evidence

1. **Loopback only.** The broker is published on `127.0.0.1`, so the ESP32-S3 cannot connect yet. Phase 7 must change the binding and enable authentication.
2. **Anonymous access.** No username/password or TLS. Acceptable for local development only.
3. **Application-level coverage is Phase 2 only.** Schema constraints, authentication and ownership are tested. Telemetry ingestion, command handling, acknowledgements and protection logic are not implemented yet, so they cannot be tested.
4. **No hardware tests.** Meter communication, relay switching, thresholds and isolation have not been verified by software. A software test cannot establish electrical safety.
5. **Persistence scope.** Mosquitto retained messages and PostgreSQL rows both survive a restart. Telemetry retention/compression policies are not implemented.
6. **Docker must be started manually.** The containers do not start after a Windows reboot until Docker Desktop is launched.
7. **OneDrive path.** The project lives inside a synced OneDrive folder. OneDrive may lock files or slow Docker bind mounts; if problems appear, exclude the folder from sync.
8. **Docker Hub CDN blocked on this network (2026-10-28).** `production.cloudfront.docker.com` resets TLS, so Docker Hub images cannot be pulled. The database uses a local fallback image built from AWS ECR's official PostgreSQL mirror plus the official TimescaleDB apt repository. Future base images may also require ECR mirrors. The official TimescaleDB image remains unverified until the network changes.
9. **Login rate limiting is in-process.** Counters are per worker and reset on restart. A multi-worker deployment needs Redis or a reverse proxy.
10. **No registration, password-reset or user-management API yet.** Accounts are created with `scripts/create_admin.py`; the first admin must be created explicitly.
11. **No command endpoint yet.** Device/channel reads are authorized, but ON/OFF commands are deliberately deferred to Phase 6 so the control path is not added before its safety rules are implemented.
12. **Starlette/httpx warning.** `TestClient` warns that `httpx` is deprecated in favour of `httpx2`. Tests pass; the dependency decision is recorded in `docs/dependencies.md`.

---

## 8. Quick troubleshooting

| Symptom | First diagnostic |
|---|---|
| `cannot find the file specified ... dockerDesktopLinuxEngine` | Start Docker Desktop and wait for the engine |
| `address already in use` on 1883 | `Get-NetTCPConnection -LocalPort 1883`; stop the conflicting process |
| Container `unhealthy` | `docker compose logs mosquitto` |
| `FAIL: cannot reach broker` | `docker compose ps`; check `127.0.0.1:1883` |
| Retained message disappears | Confirm the named volume exists; never use `docker compose down -v` casually |
| Smoke test times out | Broker running? Firewall/antivirus blocking loopback? Check logs |

For full setup/run troubleshooting, see `README.md`.

---

## 9. Planned test suites (not yet implemented)

| Phase | Suite | Examples |
|---|---|---|
| 3 | Simulator | contract-valid telemetry, command acknowledgements, fault injection, ground-truth log |
| 4 | Backend ingestion | validation, duplicate handling, persistence, WebSocket delivery, reconnect |
| 5 | Dashboard | API integration, live updates, pending/confirmed command states |
| 6 | Remote control and schedules | command timeout, safety override, schedule priority |
| 7 | Firmware (simulated and hardware) | protection thresholds, invalid/stale readings, state machine, lockout, watchdog |
| 8 | Load identification | fingerprint matching, confidence thresholds, ambiguity handling |
| 9 | AI and health score | precision, recall, F1, false-positive/negative rate, detection delay, score normalisation |
| 10 | Full integration | end-to-end latency, broker/backend restart, fault-injection campaign |

Each suite must add its commands, expected results and observed results to this document.

---

## 10. Evidence log template

Copy this table row when adding a new test:

```markdown
| Test ID | Date | Type | Command / steps | Expected | Observed | Status |
|---|---|---|---|---|---|---|
| T-XXX-000 | YYYY-MM-DD | unit/integration/fault/hardware | ... | ... | ... | PASS/FAIL/NOT RUN |
```

Artifacts (screenshots, exported logs) should be stored under `docs/evidence/` only if they add information beyond the command output, and must not contain secrets.

---

## 11. Change history

| Date | Change |
|---|---|
| 2026-10-28 | Initial document: Phase 1 broker, contract and repository-hygiene tests |
| 2026-10-28 | Added Phase 2 dependency checks T-DEP-001…004; noted `httpx2` warning |
| 2026-10-28 | Coverage audit found `alembic` missing from `requirements.txt`; added and re-verified (62/62 pins) |
| 2026-10-28 | Added db service configuration; T-DB-001 blocked by Docker Hub CDN TLS filtering; no substitution made |
| 2026-10-28 | Verified database via documented local fallback build; T-DB-001 upgraded to PASS (fallback); added T-DB-002 |
| 2026-10-29 | Implemented migrations 0002–0004 and models; added T-DB-003…007 (constraints, hypertable, persistence, hostname defect) |
| 2026-10-29 | Implemented authentication and ownership enforcement; added T-AUTH-001…007 and T-API-001; full suite 44 passed |
