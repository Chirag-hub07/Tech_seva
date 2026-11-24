import { useEffect, useState } from 'react'
import { ArrowRight, BellRing, Radio } from 'lucide-react'
import { Link } from 'react-router-dom'
import RiskCard, { formatDate } from '../components/RiskCard'
import SensorCard from '../components/SensorCard'
import EmptyState from '../components/EmptyState'
import { getAlerts, getLatestMeasurements, getLatestPrediction } from '../services/api'

export default function Dashboard({ selectedPatient, patientError }) {
  const [data, setData] = useState({
    prediction: null,
    measures: [],
    alerts: [],
    loading: false,
    error: '',
  })

  useEffect(() => {
    if (!selectedPatient?.id) return

    let isSubscribed = true
    setData((prev) => ({ ...prev, loading: true, error: '' }))

    Promise.all([
      getLatestPrediction(selectedPatient.id),
      getLatestMeasurements(selectedPatient.id),
      getAlerts(selectedPatient.id),
    ])
      .then(([prediction, measures, alerts]) => {
        if (isSubscribed) {
          setData({
            prediction,
            measures,
            alerts,
            loading: false,
            error: '',
          })
        }
      })
      .catch((err) => {
        if (isSubscribed) {
          setData({
            prediction: null,
            measures: [],
            alerts: [],
            loading: false,
            error: err.message,
          })
        }
      })

    return () => {
      isSubscribed = false
    }
  }, [selectedPatient?.id])

  if (!selectedPatient) {
    return (
      <EmptyState
        title="Connect the backend to begin"
        detail={patientError || 'Ensure the FastAPI service is running at http://localhost:8000/api/v1.'}
      />
    )
  }

  const patientLabel = selectedPatient.participant_id || selectedPatient.patient_id || `Participant ${selectedPatient.id}`
  const statusLabel = selectedPatient.monitoring_status || 'Enrolled in study'

  return (
    <div className="page">
      <section className="patient-banner">
        <div>
          <p className="eyebrow">SELECTED PARTICIPANT</p>
          <h2>{patientLabel}</h2>
          <span>{selectedPatient.country ? `Cohort: ${selectedPatient.country}` : 'Country not recorded'}</span>
        </div>
        <div className="monitoring-state">
          <Radio />
          <span>Cohort status</span>
          <strong>{statusLabel}</strong>
        </div>
      </section>

      {data.error && (
        <div className="notice" role="alert">
          {data.error}
        </div>
      )}

      <RiskCard prediction={data.prediction} loading={data.loading} />

      <section className="section-heading">
        <div>
          <p className="eyebrow">LATEST RECORDED TELEMETRY</p>
          <h2>Sensor snapshot</h2>
        </div>
        <Link to="/monitoring">
          View monitoring <ArrowRight size={16} />
        </Link>
      </section>

      <div className="sensor-grid">
        {data.measures.length ? (
          data.measures.map((m) => (
            <SensorCard measurement={m} key={m.id || `${m.sensor_type}-${m.measured_at}`} />
          ))
        ) : (
          <EmptyState
            title="No recent sensor measurements"
            detail="No telemetry records are present for this participant in the database."
          />
        )}
      </div>

      <section className="two-column">
        <div className="card list-card">
          <div className="card-title">
            <div>
              <p className="eyebrow">CLINICAL NOTIFICATIONS</p>
              <h2>Alert activity</h2>
            </div>
            <BellRing />
          </div>
          {data.alerts.slice(0, 3).length ? (
            data.alerts.slice(0, 3).map((a) => (
              <div className="compact-alert" key={a.id}>
                <span className={`level-dot ${String(a.alert_level).toLowerCase()}`} />
                <div>
                  <strong>{a.alert_level || 'Risk'} alert</strong>
                  <small>
                    {a.message || 'Clinical notification'} · {formatDate(a.created_at)}
                  </small>
                </div>
              </div>
            ))
          ) : (
            <p className="muted">
              No alerts recorded for this participant. Note: The absence of alerts does not confirm clinical stability.
            </p>
          )}
        </div>

        <div className="card information-card">
          <p className="eyebrow">CLINICAL SAFETY</p>
          <h2>Decision support only</h2>
          <p>
            ExacerbAlert displays analytical model outputs from the backend. It does not diagnose COPD, assess clinical
            stability, or replace clinical assessment.
          </p>
        </div>
      </section>
    </div>
  )
}
