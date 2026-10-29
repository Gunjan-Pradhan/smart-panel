# Dependency Proposal — Phase 2

**Status:** **Installed and verified on 2026-10-28** (see §10). Original proposal retained below for audit.
**Date:** 2026-10-28
**Target interpreter:** Python 3.13.2 (existing `.venv`)

---

## 1. Why new dependencies are needed

The current environment contains the web framework (FastAPI), MQTT client (paho), and the data/ML libraries. It does **not** contain:

- a database toolkit or migration tool,
- a PostgreSQL driver,
- password hashing,
- JWT creation/verification,
- environment-settings validation,
- form parsing for the login endpoint,
- test tooling.

Without these, Phase 2 (database and authentication) cannot be implemented or tested.

---

## 2. Proposed runtime packages

| Package | Version | Purpose | Python 3.13 evidence |
|---|---|---|---|
| `SQLAlchemy` | 2.1.6 | ORM and SQL toolkit | `requires_python >=3.11`; cp313 wheels published |
| `Alembic` | 1.20.1 | Versioned schema migrations | `requires_python >=3.10`; pure-Python wheel; requires SQLAlchemy >=2.0 |
| `psycopg[binary]` | 3.3.6 | PostgreSQL driver (v3) | `psycopg_binary-3.3.6-cp313-cp313-win_amd64.whl` verified on PyPI |
| `PyJWT` | 2.15.1 | Sign/verify access tokens | `requires_python >=3.9`; pure-Python wheel |
| `argon2-cffi` | 25.1.0 | Argon2id password hashing | pure wheel; binding wheel `cp310-abi3-win_amd64` verified (stable ABI, valid on 3.13) |
| `pydantic-settings` | 2.16.2 | Typed environment configuration | `requires_python >=3.11`; requires `pydantic>=2.7` (installed: 2.14.1 ✅) |
| `python-multipart` | 0.0.32 | Form parsing required by FastAPI's `OAuth2PasswordRequestForm` | `requires_python >=3.10`; pure-Python wheel |
| `email-validator` | 2.3.0 | Validation for `pydantic.EmailStr` | `requires_python >=3.8`; pure-Python wheel |

## 3. Proposed development packages

| Package | Version | Purpose |
|---|---|---|
| `pytest` | 9.2.0 | Test runner |
| `httpx` | 0.28.1 | HTTP client used by FastAPI/Starlette `TestClient` |

`pytest-asyncio` (1.4.1 exists) is **not** required yet because the proposed architecture uses synchronous ORM sessions. Add it only if a later phase genuinely needs async tests.

---

## 4. Compatibility findings (verified 2026-10-28)

| Check | Result |
|---|---|
| Python version | 3.13.2 |
| Existing FastAPI / Starlette / Pydantic | 0.162.0 / 1.10.0 / 2.14.1 — imports succeed |
| `pydantic-settings` requirement | `pydantic>=2.7.0` — satisfied by 2.14.1 |
| `Alembic` requirement | `SQLAlchemy>=2.0` — satisfied by proposed 2.1.6 |
| `psycopg` Windows wheel | cp313 win_amd64 exists |
| Argon2 bindings on 3.13 | abi3 cp310 wheel applies to 3.13 |
| TimescaleDB image tag | `timescale/timescaledb:2.31.0-pg17` exists on Docker Hub |
| Image architecture | **Verified for the local fallback build** (amd64): PostgreSQL 17.11 from ECR + TimescaleDB 2.31.0 apt package. The official `timescale/timescaledb:2.31.0-pg17` image remains unverified because Docker Hub's CDN is blocked (see `docs/testing.md` T-DB-001). |
| Node.js / dashboard | No change required in this step |

No existing major dependency needs upgrading or downgrading. Installing the packages above should not replace FastAPI, Pydantic, NumPy, pandas or scikit-learn.

---

## 5. Architectural decisions behind the dependency list

### 5.1 Synchronous SQLAlchemy (not async)

Chosen for the MVP because:

- paho-mqtt delivers messages on its own network thread, where a normal session-per-thread pattern is straightforward;
- FastAPI runs synchronous `def` endpoints in its threadpool automatically;
- Alembic and debugging are simpler for a beginner;
- it avoids greenlet/async-session failure modes that are hard to diagnose.

The trade-off — less concurrency per worker — is irrelevant at two devices and 2 readings/second. This can be revisited with evidence if load testing later shows a problem.

### 5.2 psycopg 3 (not psycopg2)

`psycopg2-binary` historically lags new Python releases. psycopg 3 has a verified cp313 Windows wheel, supports SQLAlchemy's `postgresql+psycopg://` dialect, and is the current maintained driver.

### 5.3 Argon2id (not passlib/bcrypt)

Argon2id is the current password-hashing recommendation and `argon2-cffi` is actively maintained. `passlib` has had maintenance gaps; it is not needed.

### 5.4 PyJWT (not python-jose)

`python-jose` has a history of security and maintenance issues. PyJWT is focused, maintained, and sufficient for HS256 access tokens.

### 5.5 Deliberately not added yet

| Package | Reason for deferral |
|---|---|
| `asyncpg` / async SQLAlchemy | Not needed with the chosen sync design |
| `fastapi-users` | Hides the auth logic this project is meant to demonstrate and test |
| `APScheduler` | Schedule execution design comes in Phase 6; choose then with requirements in hand |
| `alembic-utils`, `sqlmodel` | Unnecessary abstraction for this scope |
| Any cloud SDK or paid API client | Project must run fully locally |

---

## 6. Installation plan (NOT executed)

```powershell
cd C:\Users\gunjan\OneDrive\Desktop\FINAL_PROJECT\smart-panel

# Optional safety: save the current exact environment for rollback comparison
.\.venv\Scripts\python.exe -m pip freeze > .\requirements-before-phase2.txt

# Runtime dependencies
.\.venv\Scripts\python.exe -m pip install `
  "SQLAlchemy==2.1.6" `
  "alembic==1.20.1" `
  "psycopg[binary]==3.3.6" `
  "PyJWT==2.15.1" `
  "argon2-cffi==25.1.0" `
  "pydantic-settings==2.16.2" `
  "python-multipart==0.0.32" `
  "email-validator==2.3.0"

# Test dependencies
.\.venv\Scripts\python.exe -m pip install "pytest==9.2.0" "httpx==0.28.1"
```

`requirements-before-phase2.txt` is a local rollback aid and should **not** be committed.

### Post-install verification

```powershell
.\.venv\Scripts\python.exe -c "import sqlalchemy, alembic, psycopg, jwt, argon2, pydantic_settings, multipart, email_validator, pytest, httpx; print(sqlalchemy.__version__, alembic.__version__, psycopg.__version__, jwt.__version__, pytest.__version__)"

.\.venv\Scripts\python.exe -m pip check
```

Expected:

- import line prints versions without error;
- `pip check` prints `No broken requirements found.`
- existing imports still work:

```powershell
.\.venv\Scripts\python.exe -c "import fastapi, pydantic, pandas, sklearn; print('existing stack OK')"
```

### Requirements-file strategy

- Add the runtime packages above to `requirements.txt` (pinned exact).
- Create `requirements-dev.txt` containing `-r requirements.txt`, `pytest==9.2.0`, `httpx==0.28.1`.
- Keep the full freeze only as a local snapshot, not as the primary dependency definition, to avoid resolver conflicts later.

---

## 7. Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| SQLAlchemy 2.1.6 is a new minor release | Medium | Pin exact; no async; run migration and CRUD tests before building features |
| TimescaleDB image architecture unverified | Medium | Verify with `docker pull` + `docker inspect` in Step 2.2 before migrations |
| Docker Hub network timeouts observed | Low | Retry; use the already-working Docker pull path; do not guess an image |
| Installing packages could disturb the working ML stack | Low | No upgrades requested; run `pip check` and the existing-import test afterwards |
| pytest 9 plugin incompatibilities | Low | No pytest plugins are used |
| Windows/OneDrive file locking during installs | Low | Close editors that hold `.venv` files; do not sync `.venv` |
| `argon2-cffi` source build if a wheel is missed | Low | abi3 wheel confirmed; otherwise the install error will be reported, not worked around unsafely |

---

## 8. Rollback plan

If installation causes problems:

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y SQLAlchemy alembic psycopg psycopg-binary PyJWT argon2-cffi argon2-cffi-bindings pydantic-settings python-multipart email-validator pytest httpx
.\.venv\Scripts\python.exe -m pip install -r .\requirements-before-phase2.txt
```

No system Python, global packages or Node packages are touched.

---

## 9. Approval checklist

- [x] Versions accepted (approved 2026-10-28)
- [x] Synchronous SQLAlchemy approach accepted
- [x] PostgreSQL 17 + TimescaleDB 2.31.0 accepted
- [x] Known risk recorded: Timescale image architecture verified at pull time
- [x] Permission granted to install the listed packages into `.venv`

**Once approved:** Step 2.2 will update `requirements.txt`, install, run the verification commands, then add the database service to `docker-compose.yml` — one testable increment at a time.

---

## 10. Installation result (2026-10-28)

Executed with the exact versions proposed in §2 and §3.

| Package | Installed version |
|---|---|
| SQLAlchemy | 2.1.6 |
| Alembic | 1.20.1 |
| psycopg | 3.3.6 |
| psycopg-binary | 3.3.6 |
| PyJWT | 2.15.1 |
| argon2-cffi | 25.1.0 |
| argon2-cffi-bindings | 26.1.0 |
| pydantic-settings | 2.16.2 |
| python-multipart | 0.0.32 |
| email-validator | 2.3.0 |
| pytest | 9.2.0 |
| httpx | 0.28.1 |
| Mako (Alembic dependency) | 1.4.3 |
| MarkupSafe (Mako dependency) | 3.0.4 |
| cffi / pycparser (Argon2 dependencies) | 2.1.1 / 3.12 |
| dnspython (email-validator dependency) | 2.9.0 |
| httpcore / certifi (httpx dependencies) | 1.0.9 / 2026.10.23 |
| pytest helpers (iniconfig, pluggy, colorama, pygments) | 2.3.1 / 1.7.0 / 0.4.6 / 2.21.0 |

### Verification performed

| Check | Result |
|---|---|
| `pip check` | ✅ `No broken requirements found.` |
| Imports of all new packages | ✅ PASS |
| Argon2id hash + verify round trip | ✅ PASS |
| JWT HS256 encode/decode round trip | ✅ PASS |
| SQLAlchemy dialect `postgresql+psycopg` loads | ✅ PASS |
| `pydantic-settings` instantiation | ✅ PASS |
| Email validation | ✅ PASS |
| FastAPI `TestClient` in-memory request | ✅ PASS (with warning, see below) |
| Pre-existing package versions changed | ✅ **NONE** (compared against pre-install snapshot) |
| `pip install --dry-run -r requirements-dev.txt` | ✅ All requirements satisfied |

### New warning that must be tracked

Starlette 1.10 prints:

```
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated;
install `httpx2` instead.
```

- `httpx` 0.28.1 still works, so Phase 2 is not blocked.
- Starlette 1.10 prefers `httpx2` (2.16.0 exists, requires Python ≥3.11).
- **Not installed**, because it was not part of the approved list.
- Recommendation: before writing substantial API tests (Phase 4), either install `httpx2==2.16.0` and switch `TestClient` usage, or pin behaviour explicitly. Decide with evidence then, not silently.

### Files updated

- `requirements.txt` — runtime pins (direct and transitive)
- `requirements-dev.txt` — `-r requirements.txt` plus test tooling
- Local rollback snapshot saved **outside** the repository at `%TEMP%\smart-panel-before-phase2.txt`

### Database image note (added after installation)

Docker Hub's CDN is blocked on this network, so the official TimescaleDB image
could not be pulled. A documented fallback image is now built locally from
AWS ECR's official PostgreSQL mirror plus the official TimescaleDB apt
repository (`db/Dockerfile`). The database container was verified healthy with
PostgreSQL 17.11 and TimescaleDB 2.31.0. See `docs/testing.md` T-DB-001/T-DB-002.

No models or migrations exist yet.
