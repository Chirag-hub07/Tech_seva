# ExacerbAlert — Pre-Commit Engineering Audit Report

**Audit Date:** 2026-11-24
**Auditor:** Senior Software Architect & Engineering Lead
**Branch:** `feature/backend-fastapi`
**Current HEAD Commit:** `5adff2b5fab04a526bb60ab337d86ac090cd1f7b` (tracking `main`)
**Audit Purpose:** Comprehensive read-only review of all changes on `feature/backend-fastapi` prior to staging and commit.

---

## 1. Branch Verification & Git Status

- **Active Branch:** `feature/backend-fastapi` (cut cleanly from `main` commit `5adff2b`).
- **Commit History:** Zero commits have been added on this branch yet; the branch ref is currently identical to `main`.
- **Working Tree State:**
  - 11 modified tracked files (frontend components, pages, services, and styles).
  - 32 untracked backend files (application code, schemas, routes, test suites, configuration).
  - 1 untracked frontend utility file (`frontend/src/utils/sensorMetrics.js`).
  - 1 untracked configuration file (`pytest.ini`).
  - 8 untracked markdown audit and integration reports.
  - Zero files staged in index.

---

## 2. Complete Changed-File Inventory

### A. Modified Tracked Files (11 Files)
All modified files belong strictly to `frontend/src/` for Phase 2B API integration and clinical presentation safeguards:

| File Path | Insertion/Deletion | Role & Changes |
| :--- | :--- | :--- |
| `frontend/src/components/AlertCard.jsx` | +24 / -2 | Clinical formatting for alert cards; disables acknowledge button in live mode to protect DB immutability. |
| `frontend/src/components/RiskCard.jsx` | +65 / -10 | Prevents converting missing probabilities to 0%; displays *"Awaiting prediction"* when prediction is null. |
| `frontend/src/components/SensorCard.jsx` | +42 / -4 | Extracts primary clinical metrics via `extractPrimaryMetric()`; distinguishes Valid, Invalid (`*` QC tag), and Unverified. |
| `frontend/src/components/SensorChart.jsx` | +97 / -9 | Deterministic metric plotting via `getChartNumericKey()`; handles null observations without zero-clipping; flags invalid observations in tooltips. |
| `frontend/src/pages/Alerts.jsx` | +101 / -10 | Empty state clinical safety disclaimer (*"The absence of alerts does not confirm clinical stability"*); in-flight request cancellation. |
| `frontend/src/pages/Dashboard.jsx` | +156 / -16 | Replaces fabricated `'Active'` with `'Enrolled in study'`; prevents race conditions when switching patients; handles API errors explicitly. |
| `frontend/src/pages/PatientDetails.jsx` | +85 / -2 | Accurate cohort metadata; replaces hardcoded `'Active'` status with `'Not recorded in cohort dataset'`. |
| `frontend/src/pages/Predictions.jsx` | +107 / -5 | Awaiting prediction empty state; explicit note that all risk scores are computed by backend ML models. |
| `frontend/src/pages/SensorMonitoring.jsx` | +169 / -14 | Full 6-range support (`7d`, `14d`, `30d`, `60d`, `90d`, `all`); anchored to patient's latest observation date; request cancellation. |
| `frontend/src/services/api.js` | +116 / -17 | Structured error handling for HTTP 404, 422, 500; network error diagnostics; pagination query params; eliminates silent demo fallback. |
| `frontend/src/styles/index.css` | +2 / -2 | Adds `.unverified` and `.invalid-reading` styling for data quality tags. |

### B. Untracked Production Files to be Committed

#### Backend Core & Application (23 Files):
- `backend/.gitignore` — Ignores `.env`, `__pycache__`, and test artifacts.
- `backend/.env.example` — Safe configuration template with placeholders (no credentials).
- `backend/requirements.txt` — Pinned production and test dependencies.
- `backend/README.md` — Backend architecture, environment config, endpoint catalogue, and test commands.
- `backend/verify_connection.py` — Safe database connectivity verification script.
- `backend/__init__.py`
- `backend/app/__init__.py`
- `backend/app/config.py` — Pydantic `BaseSettings` loading `backend/.env`.
- `backend/app/database.py` — Synchronous SQLAlchemy engine with psycopg and read-only inspection.
- `backend/app/main.py` — FastAPI application factory, CORS middleware, centralized exception handler registration, router includes.
- `backend/app/models.py` — SQLAlchemy ORM declarative models strictly mapping the 6 verified Supabase tables.
- `backend/app/core/__init__.py`
- `backend/app/core/exceptions.py` — Centralized JSON error envelopes (`AppException`, `StarletteHTTPException`, `RequestValidationError`).
- `backend/app/schemas/__init__.py`
- `backend/app/schemas/patient.py` — `PatientResponse`, `PatientListResponse`.
- `backend/app/schemas/prediction.py` — `PredictionResponse`, `PredictionHistoryResponse`.
- `backend/app/schemas/measurement.py` — `SensorType`, `TimeRange`, `SensorMeasurementResponse`, `LatestMeasurementsResponse`, `MeasurementListResponse`.
- `backend/app/schemas/alert.py` — `AlertStatus`, `AlertLevel`, `AlertResponse`, `AlertListResponse`.
- `backend/app/api/__init__.py`
- `backend/app/api/routes/__init__.py`
- `backend/app/api/routes/health.py` — `/health` and `/api/v1/health` with live DB ping.
- `backend/app/api/routes/patients.py` — `GET /api/v1/patients`, `GET /api/v1/patients/{id}`.
- `backend/app/api/routes/predictions.py` — `GET /api/v1/patients/{id}/predictions/latest`, `GET /api/v1/patients/{id}/predictions`.
- `backend/app/api/routes/measurements.py` — `GET /api/v1/patients/{id}/measurements/latest`, `GET /api/v1/patients/{id}/measurements`.
- `backend/app/api/routes/alerts.py` — `GET /api/v1/patients/{id}/alerts`.

#### Backend Automated Test Suite (9 Files):
- `pytest.ini` — Root test discovery and Python path configuration.
- `backend/tests/__init__.py`
- `backend/tests/conftest.py` — TestClient fixtures and test settings.
- `backend/tests/test_health.py` — 8 tests covering health status, CORS preflight, OpenAPI schema, and 404 handler.
- `backend/tests/test_patients.py` — 4 unit tests covering patient listing, pagination, and ID lookups.
- `backend/tests/test_predictions.py` — 4 unit tests covering prediction latest, null prediction handling, and history.
- `backend/tests/test_measurements.py` — 7 unit tests covering 8-sensor latest, 7d/all range series, invalid enum validation, and 404s.
- `backend/tests/test_alerts.py` — 5 unit tests covering alert filtering by status, empty alerts, invalid status 422, and 404s.
- `backend/tests/test_live_supabase.py` — 8 integration tests querying the real Supabase database safely.

#### Frontend Utilities (1 File):
- `frontend/src/utils/sensorMetrics.js` — Clinical metric mapping dictionary (`SENSOR_DEFINITIONS`, `extractPrimaryMetric`, `getChartNumericKey`).

---

## 3. Security & Secrets Containment Audit

| Secret / Config File | Git Status | Security Verification Findings |
| :--- | :--- | :--- |
| `backend/.env` | **Ignored** | Confirmed ignored by `backend/.gitignore:2`. Contains live Supabase credentials; strictly untracked. |
| `frontend/.env` | **Ignored** | Confirmed ignored by `frontend/.gitignore:3`. Contains local development variables; strictly untracked. |
| `backend/.env.example` | Untracked (to be committed) | Contains strictly safe placeholder values (`postgres.placeholder:placeholder_password@...`). |
| `frontend/.env.example` | Tracked | Contains safe local placeholders (`http://localhost:8000/api/v1`, `VITE_DEMO_MODE=false`). |
| Codebase Credential Scan | Clean | Scanned all tracked and untracked code files. Zero hardcoded passwords, connection strings, or API tokens found. |
| API Authentication Exposure | **Identified** | All `/api/v1` routes currently operate without bearer token authentication. CORS limits browser origins to `localhost:5173`, but direct HTTP clients can query the API unauthenticated. Scheduled for Supabase JWT integration in Phase 3. |

---

## 4. Backend Review & Automated Test Results

### Schema Verification:
All six SQLAlchemy models in `backend/app/models.py` strictly mirror the live Supabase PostgreSQL schema:
- `patients`: `id`, `participant_id`, `country`, `created_at`
- `sensor_measurements`: `id`, `patient_id`, `sensor_type`, `measured_at`, `measurements`, `is_valid`, `validity_flags`, `source_record_id`, `created_at`
- `clinical_assessments`: `id`, `patient_id`, `visit_type`, `visit_date`, `clinical_data`, `created_at`, `source_record_id`
- `exacerbations`: `id`, `patient_id`, `event_timestamp`, `severity`, `source_event_id`, `created_at`, `event_data`
- `predictions`: `id`, `patient_id`, `prediction_timestamp`, `prediction_horizon_days`, `risk_probability`, `risk_level`, `model_version`, `input_window_start`, `input_window_end`, `created_at`
- `alerts`: `id`, `patient_id`, `prediction_id`, `alert_level`, `message`, `status`, `created_at`, `acknowledged_at`, `resolved_at`, `deduplication_key`

### Test Suite Execution:
```text
pytest backend/tests -v
======================= 36 passed, 4 warnings in 51.86s =======================
```
- **Total Tests:** 36
- **Passed:** 36 (100% pass rate)
- **Failed:** 0
- **Warnings:** 4 (1 upstream Starlette TestClient httpx warning, 3 deprecation notices regarding `HTTP_422_UNPROCESSABLE_ENTITY` vs `HTTP_422_UNPROCESSABLE_CONTENT`).

---

## 5. Frontend Review & Production Build Results

### Functional Checks:
1. **Live Mode & Demo Mode:** Controlled via `VITE_DEMO_MODE` in `frontend/.env`. Both verified in browser subagent testing.
2. **Patient Switching:** In-flight request cancellation (`isSubscribed`) prevents race conditions and stale telemetry display.
3. **Clinical Presentation:** Invalid sensor observations are clearly tagged (`*` QC indicator). Missing values display as `'—'` rather than converting to zero. Empty predictions render the awaiting state. Empty alerts explicitly state that zero alerts does not confirm clinical stability.

### Production Build:
```text
> exacerbalert-frontend@1.0.0 build
> vite build

vite v5.4.21 building for production...
transforming...
✓ 2760 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.47 kB │ gzip:   0.31 kB
dist/assets/index-C5_265tv.css   28.04 kB │ gzip:   6.73 kB
dist/assets/index-B5qMJFLc.js   608.40 kB │ gzip: 176.29 kB
✓ built in 21.89s
```
- **Build Status:** Passing with zero compile errors.

---

## 6. Database Safety & Immutability Findings

Direct database query auditing confirmed zero writes to the live Supabase PostgreSQL database across all phases:

| Table Name | Baseline Count | Current Count | Mutating Queries Executed |
| :--- | :--- | :--- | :--- |
| `patients` | 74 | 74 | 0 |
| `sensor_measurements` | 91,794 | 91,794 | 0 |
| `clinical_assessments` | 224 | 224 | 0 |
| `exacerbations` | 39 | 39 | 0 |
| `predictions` | 0 | 0 | 0 |
| `alerts` | 0 | 0 | 0 |
| **Total Rows** | **92,131** | **92,131** | **0 (Zero writes / Zero DDL)** |

- `Base.metadata.create_all()` is strictly confined to in-memory SQLite unit test fixtures.
- All live Supabase integration tests use HTTP `GET` queries only.

---

## 7. Documentation Disposition & MongoDB Conflict Analysis

### A. Architectural Conflict Analysis (Supabase PostgreSQL vs. Outdated MongoDB Recommendations)
During the initial repository audit (Phase 0), early planning documents referenced a conceptual MongoDB architecture. Subsequently, the user established the **strict active architecture**:
> *"Use the existing Supabase PostgreSQL database. Do NOT introduce MongoDB, SQLite, a second database, or an alternative persistence architecture."*

Multiple early audit markdown files contain **outdated recommendations that directly conflict with the active Supabase PostgreSQL architecture**:

| File | Outdated / Contradictory Content | Conflict Explanation |
| :--- | :--- | :--- |
| `ARCHITECTURE_AS_IS.md` | Lines 14, 20, 50, 96, 143 | Asserts that MongoDB is the "mandated target architecture" and treats the lack of MongoDB as a critical deficiency. |
| `COPD_PROJECT_READINESS.md` | Lines 40, 42, 64–72 | Recommends provisioning MongoDB Atlas, writing Motor/Beanie ODM models, and migrating relational tables to MongoDB time-series collections. |
| `RECOMMENDED_BRANCH_STRATEGY.md` | Lines 76, 119, 126, 141, 188–189, 217 | Assigns team roles to build MongoDB backends, suggests `feature/api-mongodb-persistence` branch, and specifies Docker Compose with MongoDB. |
| `REPOSITORY_AUDIT_REPORT.md` | Lines 21, 240 | States that MongoDB models must be built from scratch. |

### B. Classification of Untracked Markdown Files

1. **Required Technical Documentation (Keep & Commit):**
   - `backend/README.md` — Active backend documentation.
   - `PHASE_2A_TECHNICAL_REVIEW.md` — Phase 2A technical audit and database index verification.
   - `PHASE_2B_INTEGRATION_REPORT.md` — Phase 2B frontend/backend integration and clinical data presentation report.
   - `PRE_COMMIT_AUDIT.md` — This pre-commit audit report.

2. **Historical Audit Documentation (Optional Archive):**
   - `BRANCH_COMPARISON.md` — Code comparison of legacy merged branches.
   - `TECHNICAL_DEBT_AND_SECURITY.md` — Pre-existing codebase security review.

3. **Superseded / Contradictory Documentation (Do Not Commit to Mainline without Revisions):**
   - `ARCHITECTURE_AS_IS.md` — Superseded by active Supabase architecture.
   - `COPD_PROJECT_READINESS.md` — Contradicts Supabase architecture.
   - `RECOMMENDED_BRANCH_STRATEGY.md` — Proposes MongoDB branches and sprint tasks.
   - *Recommendation:* Do not stage these 3 files in the production commits, or revise them to reflect the verified Supabase PostgreSQL stack.

---

## 8. Exact Recommended Git Staging Commands

To keep Git history clean, logical, and bisectable, changes should be staged in three distinct atomic commits:

### Step 1: Commit Backend Foundation & Phase 2A Endpoints
```powershell
# Stage backend application, schemas, routes, configuration, and test suites
git add pytest.ini
git add backend/.gitignore
git add backend/.env.example
git add backend/requirements.txt
git add backend/README.md
git add backend/verify_connection.py
git add backend/__init__.py
git add backend/app/
git add backend/tests/

# Review staged files (confirm backend/.env is NOT staged)
git status

# Commit backend foundation
git commit -m "feat(backend): establish FastAPI backend and Phase 2A read-only REST endpoints

- Implement synchronous SQLAlchemy models matching 6 verified Supabase tables
- Create Pydantic v2 validation schemas for patients, predictions, telemetry, and alerts
- Add read-only REST API endpoints under /api/v1
- Configure CORS, centralized JSON error envelopes, and PostgreSQL distinct-on queries
- Add 36 automated unit and live Supabase read-only tests with 100% pass rate"
```

### Step 2: Commit Frontend Integration & Clinical Presentation Safeguards
```powershell
# Stage frontend utility and modified UI components
git add frontend/src/utils/sensorMetrics.js
git add frontend/src/services/api.js
git add frontend/src/components/AlertCard.jsx
git add frontend/src/components/RiskCard.jsx
git add frontend/src/components/SensorCard.jsx
git add frontend/src/components/SensorChart.jsx
git add frontend/src/pages/Alerts.jsx
git add frontend/src/pages/Dashboard.jsx
git add frontend/src/pages/PatientDetails.jsx
git add frontend/src/pages/Predictions.jsx
git add frontend/src/pages/SensorMonitoring.jsx
git add frontend/src/styles/index.css

# Review staged files (confirm frontend/.env and frontend/dist are NOT staged)
git status

# Commit frontend integration
git commit -m "feat(frontend): connect React dashboard to FastAPI backend with clinical safeguards

- Implement explicit TOLIFE sensor-to-metric mappings in sensorMetrics.js
- Connect Dashboard, Sensor Monitoring, Predictions, Alerts, and Patient Details to API
- Support 6 historical range windows (7d, 14d, 30d, 60d, 90d, all) anchored to latest telemetry
- Add in-flight request cancellation to prevent stale data on patient switching
- Enforce clinical data presentation rules (no zero-filling, tri-state validity tags, disclaimers)
- Support independent Live Mode and Demo Mode via environment configuration"
```

### Step 3: Commit Phase 2 Documentation (Optional)
```powershell
# Stage technical review, integration report, and pre-commit audit
git add PHASE_2A_TECHNICAL_REVIEW.md
git add PHASE_2B_INTEGRATION_REPORT.md
git add PRE_COMMIT_AUDIT.md

# Commit documentation
git commit -m "docs: add Phase 2A technical review, Phase 2B integration report, and pre-commit audit"
```

---

## 9. Final Pre-Commit Sign-Off

- **Code Quality:** All 36 backend tests pass; frontend build succeeds cleanly in 21s.
- **Data Safety:** Zero database mutations across 92,131 verified rows.
- **Secrets:** All `.env` files are strictly ignored and absent from staging.
- **Architectural Alignment:** The codebase adheres 100% to the verified Supabase PostgreSQL stack.
- **Readiness:** **APPROVED FOR COMMIT**
