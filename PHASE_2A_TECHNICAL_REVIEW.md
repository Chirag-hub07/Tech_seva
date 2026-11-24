# ExacerbAlert Phase 2A — Final Technical Review

**Review Date:** 2026-11-24
**Branch:** `feature/backend-fastapi`
**Base Commit:** `5adff2b` (identical to `main`)
**Auditor:** Senior Software Architect & Backend Engineering Lead
**Scope:** Phase 2A Read-Only REST API Endpoints, SQLAlchemy ORM Models, Schemas, Unit & Live Integration Test Suites, and Frontend Integration Contracts.

---

## 1. Executive Summary

Phase 2A established five core read-only REST API endpoints designed to serve COPD participant data, latest ML predictions, multi-stream sensor telemetry, historical sensor series, and clinical alerts from the live Supabase PostgreSQL database to the React 18 + Vite frontend.

This comprehensive technical audit evaluated the implementation against 10 strict architectural, clinical, and security criteria. The test suite of 36 automated tests (28 unit/mock tests and 8 live database tests) demonstrates a 100% pass rate. Direct verification against the live Supabase instance confirmed that the 92,131 baseline database records remain completely untouched (zero inserts, updates, deletes, or DDL migrations).

The backend endpoints precisely adhere to the contracts expected by `frontend/src/services/api.js` and the corresponding UI components (`Dashboard.jsx`, `SensorMonitoring.jsx`, `Predictions.jsx`, `Alerts.jsx`, `PatientDetails.jsx`).

---

## 2. Detailed Technical Inspection (10 Core Checks)

### Check 1: Identification and Explanation of Pytest Warnings

During full test suite execution, pytest outputs 4 warnings across 36 tests:

```text
============================== warnings summary ===============================
..\..\..\AppData\Local\Programs\Python\Python313\Lib\site-packages\fastapi\testclient.py:1
  StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient

backend/tests/test_alerts.py::test_list_alerts_invalid_status_422
backend/tests/test_measurements.py::test_invalid_sensor_type_returns_422
backend/tests/test_measurements.py::test_invalid_range_returns_422
  StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    response = await handler(conn, exc)
```

#### Root Cause Analysis:
1. **Warning 1 (`fastapi/testclient.py:1`):**
   - **Mechanism:** Starlette's `TestClient` is in the process of migrating its internal HTTP client layer. In current releases of Starlette/FastAPI, importing `TestClient` produces an informational deprecation notice regarding the transition toward `httpx2`.
   - **Impact:** Informational only. No runtime impact on test execution or backend application code.
2. **Warnings 2, 3, and 4 (`HTTP_422_UNPROCESSABLE_ENTITY` in `test_alerts.py` and `test_measurements.py`):
   - **Mechanism:** In RFC 9110 (which obsoletes RFC 7231 and WebDAV RFC 4918 status codes), status code 422 was updated from "Unprocessable Entity" to "Unprocessable Content". Starlette has marked `status.HTTP_422_UNPROCESSABLE_ENTITY` as deprecated in favor of `status.HTTP_422_UNPROCESSABLE_CONTENT`.
   - **Location:** `backend/app/core/exceptions.py:76` in `validation_exception_handler()`:
     ```python
     return JSONResponse(
         status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,  # <- triggers deprecation warning
         content={...}
     )
     ```
   - **Impact:** Low. The HTTP status code emitted over the wire remains numeric `422`, which standard clients and browsers handle identically. Updating to `status.HTTP_422_UNPROCESSABLE_CONTENT` eliminates all three warnings cleanly.

---

### Check 2: Verification of Backend Responses Against Frontend Contracts

Every backend response was compared against `frontend/src/services/api.js` and the consuming UI components:

| Endpoint | Backend Return Type | Frontend Helper (`api.js`) | Frontend Consumer | Compatibility Status |
| :--- | :--- | :--- | :--- | :--- |
| `GET /api/v1/patients` | `PatientListResponse` (`{ items: [...], total, limit, offset }`) | `getPatients()` unwraps via `asArray(val) => val?.items` | `App.jsx`, `PatientSelector.jsx`, `PatientDetails.jsx` | **Verified Fully Compatible** |
| `GET /api/v1/patients/{id}` | `PatientResponse` (`{ id, participant_id, country, created_at }`) | `getPatient(id)` | Direct fetch | **Verified Fully Compatible** |
| `GET /api/v1/patients/{id}/predictions/latest` | `Optional[PredictionResponse]` (returns object or `null`) | `getLatestPrediction(id)` | `Dashboard.jsx` -> `RiskCard.jsx` | **Verified Fully Compatible** |
| `GET /api/v1/patients/{id}/predictions` | `PredictionHistoryResponse` (`{ items: [...], total, limit, offset }`) | `getPredictionHistory(id)` unwraps `asArray(val)` | `Predictions.jsx` table | **Verified Fully Compatible** |
| `GET /api/v1/patients/{id}/measurements/latest` | `LatestMeasurementsResponse` (`{ items: [...], patient_id, total_sensors }`) | `getLatestMeasurements(id)` unwraps `asArray(val)` | `Dashboard.jsx` -> `SensorCard.jsx` | **Verified Fully Compatible** |
| `GET /api/v1/patients/{id}/measurements` | `MeasurementListResponse` (`{ items: [...], total, sensor_type, range, limit, offset }`) | `getMeasurements(id, sensor, range)` unwraps `asArray(val)` | `SensorMonitoring.jsx` -> `SensorChart.jsx` | **Verified Fully Compatible** |
| `GET /api/v1/patients/{id}/alerts` | `AlertListResponse` (`{ items: [...], total, limit, offset }`) | `getAlerts(id)` unwraps `asArray(val)` | `Dashboard.jsx`, `Alerts.jsx` -> `AlertCard.jsx` | **Verified Fully Compatible** |

#### Consuming Field Alignment:
- **`Patient`:** UI accesses `participant_id`, `country`, `created_at`, `id`. Backend delivers all four. UI falls back to `monitoring_status || 'Active'`.
- **`RiskCard`:** Evaluates `prediction.risk_probability`, `prediction.risk_level`, `prediction.prediction_horizon_days`, `prediction.prediction_timestamp || prediction.created_at`. When `null`, displays *"Awaiting prediction"*. Backend matches this contract exactly.
- **`SensorCard` & `SensorChart`:** Consumes `m.sensor_type`, `m.measured_at`, `m.is_valid`, and iterates `Object.entries(m.measurements)[0]`. Backend returns the unmutated JSONB dictionary.
- **`AlertCard`:** Consumes `alert.alert_level`, `alert.message`, `alert.status`, `alert.created_at`. Backend delivers all four.

---

### Check 3: Historical Telemetry Range Anchoring Verification

- **Code Location:** `backend/app/api/routes/measurements.py:123-145`
- **Implementation:**
  ```python
  base_filter = [
      SensorMeasurement.patient_id == patient_id,
      SensorMeasurement.sensor_type == sensor_type.value,
  ]
  if range != TimeRange.ALL:
      latest_ts = db.scalar(
          select(func.max(SensorMeasurement.measured_at)).where(*base_filter)
      )
      if latest_ts:
          delta_days = days_lookup.get(range, 7)
          cutoff = latest_ts - timedelta(days=delta_days)
          base_filter.append(SensorMeasurement.measured_at >= cutoff)
  ```
- **Confirmation:** The query strictly calculates `func.max(SensorMeasurement.measured_at)` filtered by both `patient_id` AND `sensor_type`. It anchors the trailing window to that specific stream's latest observation rather than wall-clock `datetime.now()`.
- **Clinical Significance:** Because the TOLIFE research dataset contains historical biometric data recorded between April 2024 and May 2025, anchoring against wall-clock `now()` would return zero records. Stream-anchoring accurately isolates the final 7, 14, 30, 60, or 90 days of recorded telemetry for every participant.

---

### Check 4: Documentation of Time Range Semantics

The `range` parameter accepts values from enum `TimeRange` (`backend/app/schemas/measurement.py:22`):

1. **`7d` (`TimeRange.SEVEN_DAYS`):** Filters for records where `measured_at >= max(measured_at) - 7 days`. Captures high-resolution acute changes in the final week of monitoring.
2. **`14d` (`TimeRange.FOURTEEN_DAYS`):** Filters for records where `measured_at >= max(measured_at) - 14 days`. Standard two-week sub-acute clinical baseline window.
3. **`30d` (`TimeRange.THIRTY_DAYS`):** Filters for records where `measured_at >= max(measured_at) - 30 days`. Monthly longitudinal trend analysis window.
4. **`60d` (`TimeRange.SIXTY_DAYS`):** Filters for records where `measured_at >= max(measured_at) - 60 days`. Two-month bi-cycle observation window.
5. **`90d` (`TimeRange.NINETY_DAYS`):** Filters for records where `measured_at >= max(measured_at) - 90 days`. Quarterly clinical assessment cycle window matching typical clinical follow-up intervals.
6. **`all` (`TimeRange.ALL`):** Omits the `measured_at >= cutoff` filter clause entirely; streams all records across the full study duration for that patient and sensor.
7. **Ordering Guarantee:** All queries enforce `ORDER BY measured_at ASC, id ASC` so that data arrays feed directly into chronological time-series chart renderers without frontend re-sorting.

---

### Check 5: Preservation of Telemetry JSONB, Validity Flags, and Timestamps

- **Schema Definition:** `backend/app/schemas/measurement.py:33-46`
- **Model Definition:** `backend/app/models.py:81-110`
- **Data Inspection:**
  - `measurements`: Stored as PostgreSQL `JSONB`, defined as `Column(JSONB, nullable=False)`. Validated by Pydantic as `Dict[str, Any]`. Preserves original metric keys (e.g., `rf_mean`, `rf_max`, `Max_AQI`, `RMSSD`, `nRMSSD`, `hr_mean`, `sleep_duration`) with native floating-point and integer types without stringification or numeric clipping.
  - `validity_flags`: Stored as PostgreSQL `JSONB`, defined as `Column(JSONB, nullable=True)`. Validated as `Optional[Dict[str, Any]]`. Raw index validity metrics (e.g. `{"data_validity": 1.0, "index_validity": 1.0}`) are preserved.
  - `is_valid`: Stored as `Column(Boolean, nullable=True)`. Handled as `Optional[bool]`. Retains tri-state logic (`True`, `False`, or `None` if uncomputed).
  - `measured_at` & `created_at`: Defined as `Column(DateTime(timezone=True))`. Serialized as ISO-8601 strings with full UTC offsets (e.g. `"2024-06-05T20:00:00.018000Z"`). Microsecond precision is preserved.
- **Verification:** Live queries against Patient 1 PRVI, BRI, and PEI records confirmed zero silent data conversion or precision loss.

---

### Check 6: Clinical Representation of Missing Predictions and Alerts

- **Missing Predictions:**
  - **Nonexistent Patient:** If `patient_id` does not exist in `patients`, the endpoint raises `HTTPException(404, "Patient with ID {id} not found.")`.
  - **Existing Patient Without Predictions:** The live Supabase database currently contains 0 records in `predictions`. The endpoint returns `status_code=200` with body `null`.
  - **Clinical Justification:** Distinguishes between an invalid patient ID and a newly enrolled or unassessed patient awaiting their initial model run.
- **Missing Alerts:**
  - **Nonexistent Patient:** Returns `404 Not Found`.
  - **Existing Patient Without Alerts:** The live database currently contains 0 records in `alerts`. The endpoint returns `status_code=200` with body:
    ```json
    {
      "items": [],
      "total": 0,
      "limit": 100,
      "offset": 0
    }
    ```
  - **Clinical Justification:** A patient with zero active alerts is clinically healthy / in steady state. Returning an empty list represents this clean state without triggering client-side error boundaries.

---

### Check 7: Authentication, Authorization, and Route Exposure Analysis

- **Inspection Location:** `backend/app/main.py`, `backend/app/api/routes/*.py`
- **Current State:**
  - **Zero Authentication:** No JWT validation, OAuth2 bearer tokens, API key headers, or session cookies are required on any `/api/v1/*` routes.
  - **CORS Protection:** Configured with `allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"]`, `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.
- **Security Implications:**
  - CORS only restricts cross-origin JavaScript requests executing inside web browsers. It provides **zero protection** against non-browser requests (e.g., `curl`, Python `requests`, Postman, automated scanners, or compromised internal network processes).
  - Anyone with network connectivity to port 8000 can enumerate all 74 COPD participants, extract full sensor telemetry series, and read clinical alerts.
  - **Severity:** Classified as **High** for production deployment; acceptable strictly for local Phase 2A development.

---

### Check 8: Live Supabase Test Suite Immutability and Safety Guarantees

- **Test Suite Location:** `backend/tests/test_live_supabase.py`
- **Safety Safeguards Verified:**
  1. **Strictly HTTP GET Invocations:** The test suite issues only `self.client.get(...)` requests.
  2. **Zero Mutation Logic:** None of the route handlers invoked by the test suite contain `INSERT`, `UPDATE`, `DELETE`, `session.add()`, or `session.commit()` operations.
  3. **No DDL in Application or Live Tests:** `Base.metadata.create_all()` is never executed on the live Supabase engine. Only SQLite in-memory test fixtures in `test_patients.py`, `test_predictions.py`, `test_measurements.py`, and `test_alerts.py` create transient tables on `sqlite:///:memory:`.
  4. **Row Count Audit:** Row counts were checked before and after all test runs:
     - `patients`: 74 -> 74
     - `sensor_measurements`: 91,794 -> 91,794
     - `clinical_assessments`: 224 -> 224
     - `exacerbations`: 39 -> 39
     - `predictions`: 0 -> 0
     - `alerts`: 0 -> 0
     - **Delta: 0 across all 92,131 rows.**

---

### Check 9: Database Indexing, Query Performance, and Pagination Analysis

Live inspection of Supabase PostgreSQL indexes revealed optimal alignment with Phase 2A queries:

| Table | Index Name | Columns Indexed | Query Optimality |
| :--- | :--- | :--- | :--- |
| `sensor_measurements` | `idx_sensor_history` | `(patient_id, sensor_type, measured_at DESC)` | **Optimal.** Directly accelerates both `GET /measurements/latest` (`DISTINCT ON`) and `GET /measurements` series range queries. |
| `sensor_measurements` | `idx_sensor_patient` | `(patient_id)` | Enables instant foreign key scans and count queries. |
| `predictions` | `idx_prediction_history` | `(patient_id, prediction_timestamp DESC)` | **Optimal.** Enables instant single-row index scan for `GET /predictions/latest`. |
| `alerts` | `idx_alert_status` | `(patient_id, status)` | **Optimal.** Directly covers filtered queries (`GET /alerts?status=pending`). |
| `alerts` | `idx_alert_created` | `(created_at DESC)` | Optimizes global timeline ordering. |
| `patients` | `patients_participant_id_key` | `(participant_id)` (Unique) | Accelerates unique participant ID lookups. |

#### Pagination Bounds:
- `limit` parameters are strictly guarded with Pydantic `ge=1, le=500` (patients, alerts) and `ge=1, le=1000` (telemetry series).
- `offset` parameters are guarded with `ge=0`.
- All list endpoints provide `{ total, limit, offset }` pagination metadata.

---

### Check 10: Git Status, Secrets Containment, and Branch Cleanliness

- **Branch:** `feature/backend-fastapi`
- **Branch Head:** `5adff2b` (Zero unauthorized commits or pushes).
- **Working Tree Cleanliness:**
  - Zero modifications to tracked files.
  - Zero frontend files staged, altered, or added.
  - `backend/.env` is strictly untracked and verified ignored by root `.gitignore` (`!! backend/.env`).
  - No secret tokens, database connection strings, or service keys exist in Git staging or commit logs.

---

## 3. Classification of Findings

| Severity | ID | Area | Finding Summary | Exact File & Location |
| :--- | :--- | :--- | :--- | :--- |
| **High** | SEC-01 | Security | **Unauthenticated REST Endpoints:** All `/api/v1` routes are open without token authentication, permitting unauthenticated reading of patient telemetry and clinical alerts if exposed beyond localhost. | `backend/app/main.py:46-51` |
| **Medium** | WARN-01 | Code Quality | **Starlette Status Deprecation:** `validation_exception_handler` returns deprecated `status.HTTP_422_UNPROCESSABLE_ENTITY`, triggering 3 pytest deprecation warnings. | `backend/app/core/exceptions.py:76` |
| **Low** | UX-01 | Frontend Interop | **Default Telemetry Page Limit:** `get_measurements_series` defaults to `limit=500`. For dense high-frequency streams across 90 days, data exceeding 500 records requires client pagination or setting `limit=1000`. | `backend/app/api/routes/measurements.py:108` |
| **Low** | TEST-01 | Test Quality | **Httpx Deprecation Warning in TestClient:** Importing `TestClient` produces an upstream warning regarding `httpx` vs `httpx2`. | `backend/tests/*.py` / `fastapi/testclient.py:1` |

---

## 4. Necessary Corrective Actions (Implementation Guidance)

### Corrective Action for WARN-01 (Deprecation Warning):
In `backend/app/core/exceptions.py`, update `status.HTTP_422_UNPROCESSABLE_ENTITY` to `status.HTTP_422_UNPROCESSABLE_CONTENT`:
```python
# backend/app/core/exceptions.py:76
return JSONResponse(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    content={
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request payload validation failed.",
            "details": exc.errors(),
        }
    },
)
```

### Corrective Action for SEC-01 (Authentication Roadmap for Phase 2B / Phase 3):
Implement a FastAPI dependency (`get_current_user` or Supabase JWT authenticator) in `backend/app/core/security.py` that verifies the `Authorization: Bearer <jwt>` header against Supabase auth keys before granting access to patient endpoints.

---

## 5. Final Assessment of Backend Readiness for Frontend Integration

### Verdict: **READY FOR FRONTEND INTEGRATION**

- **Contract Fidelity:** The response payloads from all 5 read-only endpoints conform exactly to the data structures consumed by `frontend/src/services/api.js` and React components.
- **Database Safety:** Zero records were altered or lost. The 92,131 clinical baseline records in Supabase remain intact and immutable.
- **Performance:** Multi-column B-tree indexes in Supabase (`idx_sensor_history`, `idx_prediction_history`, `idx_alert_status`) match query access patterns with optimal performance.
- **Test Integrity:** 36 automated tests pass with 100% success rate.
- **Isolation:** Environment credentials remain securely masked and untracked.
