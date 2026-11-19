# Redo Checklist - Dashboard Redesign Prompt v2

This checklist tracks all work that needs to be redone from the previous chat session. Each item must be completed, committed, and verified.

## Phase 0: Baseline, Truth Audit & Backend Contract Fixes
- [ ] **Step 0.1: Baseline**
  - [ ] Start full stack: docker compose up -d, scripts/seed_database.py, uvicorn, scripts/mock_esp32_device.py, npm run dev
  - [ ] Run and record: npm ci, npm run build, npm test, pytest backend/tests -q
  - [ ] Sign in as operator and viewer, screenshot all 11 views + login at 1440x900 to docs/ui/before/
  - [ ] Diff hooks/useWebSocket.js and hooks/useWebSocket.js.bak, identify live version

- [ ] **Step 0.2: Truth Audit**
  - [ ] Create docs/ui/feature_matrix.md with every on-screen element
  - [ ] Call all required endpoints and save JSON to docs/ui/api_samples/
  - [ ] Verify all 9 confirmation points (Limits, Events, Learning, Recognition, Suggestions, Modes, Schedules, Commands, Profiles, Auth, Health score, Cadence, Flags)
  - [ ] Confirm 9 additional points (Limits push, Protection events, Learning parameters, Recognise samples, Reset, Registration, Operating hours, Anomaly caller, Channel names)

- [ ] **Step 0.3: Decisions**
  - [ ] Record decisions D1-D5 in docs/ui/decisions.md

- [ ] **Step 0.4: Backend Contract Fixes (B1-B6)**
  - [ ] B1: Event times - ISO 8601 with timezone, single field name
  - [ ] B2: Anomaly guard - minimum baseline samples, floor std dev, map severity from Z
  - [ ] B3: Event de-duplication - update open event instead of inserting new rows
  - [ ] B4: Learning/recognition responses - stable named fields
  - [ ] B5: Channel limits - return limits_source (default_unverified/user_confirmed)
  - [ ] B6: Modes - GET/PUT /channels/{ch}/modes (if D1 finds mode worth keeping)
  - [ ] Add pytest for each fix, keep all tests green

**Gate 0:** Matrix complete, decisions.md written, before screenshots exist, pytest green, npm run build passes

## Phase 1: Design System v2
- [ ] 1.1 Tokens (styles/tokens.css) - Update all tokens per spec
- [ ] 1.2 Component changes (styles/components.css and components/ui)
- [ ] 1.3 Icons (lucide-react only)
- [ ] 1.4 Charts (chartTheme.js, areaFill.jsx)
- [ ] 1.5 Number/time formatting (utils/format.js with unit tests)
- [ ] 1.6 Style files (views.css, delete hud.css/App.css later)
- [ ] 1.7 DesignShowcase at ?design=1
- [ ] Gate 1: npm run test:gates passes, contrast test passes, DesignShowcase renders, screenshot saved

## Phase 2: Data Layer
- [ ] 2.1 Target structure (Root.jsx, App.jsx, router/, state/, hooks/, views/, charts/, utils/)
- [ ] 2.2 Normalised channel model in liveStore.js
- [ ] 2.3 Live store and stream hook (useLiveStream.js)
- [ ] 2.4 Command machine (state/commands.js)
- [ ] 2.5 API client and session (api/client.js, utils/errors.js)
- [ ] 2.6 Hash router (useHashRoute.js, routes.js)
- [ ] 2.7 Fetching helper and polling (useApi.js)
- [ ] 2.8 Local settings (useLocalSetting.js)
- [ ] 2.9 Error boundaries
- [ ] 2.10 Delete dead code
- [ ] Gate 2: Vitest covers normaliser, command-machine, router, format.js; App.jsx <200 lines; manual checks pass

## Phase 3: Shell
- [ ] 3.1 Page frame (sidebar, skip link, main area)
- [ ] 3.2 Top bar and status strip (pills from named sources)
- [ ] 3.3 Alert banner (conditions in priority order)
- [ ] 3.4 Drawers, toasts, dialogs
- [ ] 3.5 Responsive behaviour
- [ ] 3.6 ws_stub.mjs (dev-only, ws package)
- [ ] Gate 3: Screenshots at 1440/1024/390 in 5 states; keyboard check; gates pass

## Phase 4: Monitoring Views (6 views)
- [ ] 4.1 Overview
- [ ] 4.2 Standard Monitoring
- [ ] 4.3 Derived Parameters
- [ ] 4.4 Energy and Cost
- [ ] 4.5 Load Health
- [ ] 4.6 AI Summary
- [ ] Gate 4: Screenshots in 5 states, feature matrix updated, derived.js/summary.js tests pass

## Phase 5: Control & Intelligence Views (5 views)
- [ ] 5.1 Optimization Modes
- [ ] 5.2 AI Learning and Recognition
- [ ] 5.3 Safe Limits and Profiles
- [ ] 5.4 Schedules
- [ ] 5.5 Events
- [ ] 5.6 Retire old styles (delete hud.css, App.css, legacy aliases, old components)
- [ ] Gate 5: E2E run, role check, screenshots, hud.css/App.css gone, gates pass, adapter tests pass

## Phase 6: Login, Legal, Favicon, Launch
- [ ] 6.1 Login view
- [ ] 6.2 Registration safety check (fix backend if needed)
- [ ] 6.3 Privacy Policy page
- [ ] 6.4 Terms and Conditions page
- [ ] 6.5 Favicon and identity (create SVG, ICO, PNG, webmanifest)
- [ ] 6.6 Launch checklist (scripts/launch_check.mjs)
- [ ] Gate 6: Pages render, favicon shows, AI marks gate passes, launch_check runs

## Phase 7: Quality Gates, Tests, Final Report
- [ ] 7.1 verify_all.sh (npm run verify)
- [ ] 7.2 Scripted screenshots (Playwright, capture.mjs)
- [ ] 7.3 Missing/stale/simulated/role tests (Vitest)
- [ ] 7.4 Accessibility (axe-core, landmarks, focus, color, toasts, tables, charts, forms, reduced-motion, zoom)
- [ ] 7.5 Behaviour checks (9 checks with logs)
- [ ] 7.6 Hardware-only items listed
- [ ] 7.7 Final report (FINAL_REPORT.md)
- [ ] 7.8 Stop conditions documented
- [ ] Gate 7: npm run verify exits 0, pytest green, screenshots exist, Vitest honesty tests pass, accessibility fixed, feature matrix complete, FINAL_REPORT.md written

## Backend Fixes (B1-B6 from Phase 0)
- [ ] B1: Event times - ISO 8601 with timezone, single field
- [ ] B2: Anomaly guard - minimum baseline samples, floor std dev, Z-based severity
- [ ] B3: Event de-duplication - update open event
- [ ] B4: Learning/recognition responses - stable named fields
- [ ] B5: Channel limits - limits_source field
- [ ] B6: Modes - GET/PUT /channels/{ch}/modes (if D1 allows)

## Bug Fixes from "Known Defects"
- [ ] Fix 1: Schedules - white on white title, raw controls, button label
- [ ] Fix 2: AI Learning - faint titles, blank counts, invisible suggestions, CRITICAL tags
- [ ] Fix 3: api.startLearning(channel, true) hardcoded simulated flag
- [ ] Fix 4: Profiles - invisible titles, duplicate profiles, hardcoded caps
- [ ] Fix 5: Events - Invalid Date, all CRITICAL, same Z=105.27
- [ ] Fix 6: Overview - invented comms health, fake waveform, fake utilization
- [ ] Fix 7: Charts - flat lines, fixed axes, fake energy bars, fake x labels
- [ ] Fix 8: Standard - energy gauge scaled to 100kWh, static VALID RMS, RELAY ACTIVE
- [ ] Fix 9: Derived - PF CONSISTENT with 0.278 diff, CALIBRATED gains=1, EDGE VECTOR VERIFIED
- [ ] Fix 10: Modes - local state only, alarm red disabled
- [ ] Fix 11: AI Summary - static text
- [ ] Fix 12: Load Health - fixed 98%, fake retries, fake relay integrity
- [ ] Fix 13: Energy/Cost - invented 4000W limit, generic advice
- [ ] Fix 14: Top bar - translucent bar, crowded pills, jittering cost
- [ ] Fix 15: Sidebar - native tooltips, double highlight
- [ ] Fix 16: Device picker - shows fallback "(device)"
- [ ] Fix 17: Emoji icons
- [ ] Fix 18: useWebSocket.js - Number||0, FAULT_TRIP vs FAULT_RETRY, uptime_s, hardcoded thresholds, two versions
- [ ] Fix 19: App.jsx - 1757 lines, hooks after conditional return, 2s timer from ref, mode toggles
- [ ] Fix 20: client.js/errors.js - no token refresh, digit-matching errors

## Mock Device Fixes
- [ ] MQTT client ID uniqueness (PID + timestamp)
- [ ] Millisecond timestamp precision (ts = round(time.time(), 3))
- [ ] ACK always includes cmd_id (generate UUID if missing)
- [ ] Unique client ID (PID + timestamp)

## Backend Fixes (B1-B6)
- [ ] B1: Event timestamps - ISO 8601 with timezone
- [ ] B2: Anomaly guard - baseline samples, floor std dev, Z-based severity
- [ ] B3: Event de-duplication
- [ ] B4: Learning/recognition stable fields
- [ ] B5: Channel limits - limits_source field
- [ ] B6: Modes - GET/PUT /channels/{ch}/modes

## Documentation
- [ ] docs/ui/feature_matrix.md
- [ ] docs/ui/decisions.md
- [ ] docs/ui/api_samples/
- [ ] docs/api_contract.md
- [ ] docs/ui/not_built.md
- [ ] docs/ui/decisions.md
- [ ] docs/ui/FINAL_REPORT.md
- [ ] docs/ui/feature_matrix.md
- [ ] docs/legal_review_notes.md
- [ ] docs/deployment.md
- [ ] docs/api_contract.md
- [ ] docs/ui/after/index.md (screenshots)
- [ ] scripts/launch_check.mjs
- [ ] scripts/verify_all.sh
- [ ] scripts/capture.mjs (Playwright)
- [ ] scripts/ws_stub.mjs
- [ ] dashboard/scripts/ui_gates.sh
- [ ] dashboard/scripts/verify_all.sh
- [ ] dashboard/scripts/capture.mjs
- [ ] .github/workflows (if needed)

## Git Tags
- [ ] git tag phase-0-done
- [ ] git tag phase-1-done
- [ ] git tag phase-2-done
- [ ] git tag phase-3-done
- [ ] git tag phase-4-done
- [ ] git tag phase-5-done
- [ ] git tag phase-6-done
- [ ] git tag phase-7-done

## Git Bundle Backup
- [ ] git bundle create ../project-backup-$(date +%Y%m%d-%H%M).bundle --all (after each phase)