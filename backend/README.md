# ExacerbAlert Backend Service — Phase 1 Foundation

Production-structured Python FastAPI backend service for the **ExacerbAlert COPD Context-Aware Healthcare System**.

## 1. Architecture Overview

- **Framework:** FastAPI 0.115+
- **Database:** Supabase PostgreSQL (Port 5432 / 6543)
- **ORM:** SQLAlchemy 2.0 (Synchronous)
- **Database Driver:** `psycopg` (v3)
- **Configuration:** Pydantic Settings (Environment-based)
- **API Prefix:** `/api/v1`
- **Default Port:** `8000`
- **Allowed Frontend Origin:** `http://localhost:5173` (React 18 + Vite)

---

## 2. Directory Layout

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                     # Application entry point and lifespan manager
│   ├── config.py                   # Pydantic Settings configuration
│   ├── database.py                 # SQLAlchemy engine, session generator, metadata verifier
│   ├── models.py                   # Verified declarative models for all 6 tables
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── health.py           # Health checks (/health and /api/v1/health)
│   └── core/
│       ├── __init__.py
│       └── exceptions.py           # Centralized exception handlers
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Pytest fixtures and TestClient setup
│   └── test_health.py              # Health, CORS, Swagger, and schema tests
├── .env.example                    # Template environment variables (placeholders only)
├── .gitignore                      # Git ignore protection for .env and caches
├── requirements.txt                # Pinned production and test dependencies
└── README.md                       # This documentation
```

---

## 3. Verified Database Schema

The backend maps strictly to the existing 6 Supabase PostgreSQL tables:

1. **`patients`**: Participant master records (`participant_id`, `country`, `created_at`).
2. **`sensor_measurements`**: 8 sensor streams (BRI, EI, MI, PEI, PRVI, SHRI, SII, SQI) with JSONB `measurements` and `validity_flags`.
3. **`clinical_assessments`**: Periodic visits (T1 to T5) with JSONB `clinical_data` and `source_record_id`.
4. **`exacerbations`**: Exacerbation events (Moderate, Severe) with JSONB `event_data` and `source_event_id`.
5. **`predictions`**: Forward risk predictions (`risk_probability` 0–1, `prediction_horizon_days > 0`).
6. **`alerts`**: Risk alerts (pending, acknowledged, resolved) linked to patients and predictions.

> [!IMPORTANT]
> **Database Safety Guarantee:**
> - `Base.metadata.create_all()` is **never** executed.
> - Migrations are **never** auto-generated or applied.
> - Existing tables, constraints, records, and JSONB structures are **never** altered or deleted.

---

## 4. Setup and Installation

### Step 1: Install Dependencies

```bash
pip install -r backend/requirements.txt
```

### Step 2: Configure Environment

Copy `.env.example` to `.env`:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` to configure your Supabase connection string:

```env
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<your-password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

If `DATABASE_URL` is unset or invalid, the backend starts in standalone safe mode and clearly reports `database.status: "unconfigured"`.

---

## 5. Running the Application

### Development Server:

Run from the repository root:

```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Or run directly from inside the `backend` folder:

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The server binds to:
- **API Base:** `http://localhost:8000`
- **Swagger Documentation:** `http://localhost:8000/docs`
- **ReDoc Documentation:** `http://localhost:8000/redoc`
- **Health Check:** `http://localhost:8000/health`
- **Versioned Health Check:** `http://localhost:8000/api/v1/health`

---

## 6. Running the Automated Test Suite

Execute pytest from the repository root:

```bash
pytest backend/tests -v
```

All acceptance criteria tests verify:
- FastAPI startup
- `/health` status and response payload
- `/docs` Swagger availability
- CORS permission for `http://localhost:5173`
- Database safe metadata inspection
- Schema integrity of all 6 SQLAlchemy models
