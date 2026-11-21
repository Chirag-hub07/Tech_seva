# ExacerbAlert frontend

React/Vite dashboard for the ExacerbAlert COPD research prototype. It displays data returned by FastAPI; it does **not** calculate risk or connect directly to Supabase/PostgreSQL.

## Run locally

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Set `VITE_API_BASE_URL` in `.env` to the FastAPI API prefix (defaults to `http://localhost:8000/api/v1`).

## Backend contract

The UI expects JSON from these endpoints (array payloads may also be wrapped as `{ "items": [...] }` or `{ "data": [...] }`):

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/patients` | Patient selector |
| GET | `/patients/:id` | Patient details |
| GET | `/patients/:id/predictions/latest` | Current ML-generated risk |
| GET | `/patients/:id/predictions` | Prediction history |
| GET | `/patients/:id/measurements/latest` | Sensor snapshot |
| GET | `/patients/:id/measurements?sensor_type=BRI&range=7d` | Sensor time series |
| GET | `/patients/:id/alerts` | Alert history |
| PATCH | `/alerts/:id/acknowledge` | Acknowledge a pending alert |

Recommended prediction fields: `risk_probability` (0–1), `risk_level`, `prediction_horizon_days`, `prediction_timestamp`, and `model_version`. Recommended sensor fields: `sensor_type`, `measured_at`, `measurements`, and `is_valid`.

All network failures are surfaced as empty/error states so no clinical result is fabricated. This is a research-prototype interface, not an emergency or diagnostic tool.
