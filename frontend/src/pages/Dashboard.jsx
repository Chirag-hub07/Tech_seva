import { useEffect, useState } from 'react'
import {
  Activity,
  ArrowRight,
  BellRing,
  CheckCircle2,
  FileText,
  HeartPulse,
  Radio,
  ShieldCheck,
  Stethoscope,
  Users,
} from 'lucide-react'
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
    setData((d) => ({ ...d, loading: true, error: '' }))

    Promise.all([
      getLatestPrediction(selectedPatient.id),
      getLatestMeasurements(selectedPatient.id),
      getAlerts(selectedPatient.id),
    ])
      .then(([prediction, measures, alerts]) =>
        setData({ prediction, measures, alerts, loading: false, error: '' }),
      )
      .catch((e) =>
        setData({
          prediction: null,
          measures: [],
          alerts: [],
          loading: false,
          error: e.message,
        }),
      )
  }, [selectedPatient?.id])

  if (!selectedPatient) {
    return (
      <EmptyState
        title="Connect patient telemetry to begin"
        detail={patientError || 'Ensure VITE_API_BASE_URL is configured and the FastAPI backend service is active.'}
      />
    )
  }

  const patientId = selectedPatient.participant_id || selectedPatient.patient_id || `DEMO-00${selectedPatient.id}`
  const country = selectedPatient.country || 'International Cohort'
  const monitoringStatus = selectedPatient.monitoring_status || 'Active'

  return (
    <div className="page dashboard-page">
      {/* Unified Professional Page Header */}
      <div className="page-header-bar">
        <div className="page-header-content">
          <div className="page-header-pre">
            <span>CLINICAL SURVEILLANCE</span>
            <span className="page-header-sep">/</span>
            <span className="page-header-patient">{patientId}</span>
          </div>
          <div className="page-header-title-row">
            <h2>Patient Surveillance Overview</h2>
            <span className="page-header-badge">TOLIFE Study</span>
          </div>
          <p className="page-header-desc">
            Real-time longitudinal telemetry surveillance and early exacerbation predictive risk monitoring for enrolled COPD participants.
          </p>
        </div>

        <div className="page-header-actions">
          <div className="monitoring-status-beacon">
            <span className="beacon-dot" />
            <div className="beacon-text">
              <small>TELEMETRY LINK</small>
              <strong>{monitoringStatus} Streaming</strong>
            </div>
          </div>
        </div>
      </div>

      {/* Patient Clinical Profile Banner */}
      <section className="patient-banner">
        <div className="patient-banner-left">
          <div className="patient-avatar-box">
            <span className="patient-avatar-initials">{patientId.slice(-3)}</span>
          </div>
          <div className="patient-meta-info">
            <div className="patient-cohort-tag">
              <Stethoscope size={13} />
              <span>COPD LONGITUDINAL STUDY COHORT</span>
            </div>
            <h2>{patientId}</h2>
            <div className="patient-chips-row">
              <span className="info-chip">
                <Users size={13} />
                Region: {country}
              </span>
              <span className="info-chip">
                <Activity size={13} />
                8 Sensors Streamed
              </span>
              <span className="info-chip">
                <FileText size={13} />
                GOLD Stage III
              </span>
            </div>
          </div>
        </div>

        <div className="patient-banner-right">
          <div className="monitoring-status-beacon">
            <span className="beacon-dot" />
            <div className="beacon-text">
              <small>TELEMETRY LINK</small>
              <strong>{monitoringStatus} Streaming</strong>
            </div>
          </div>
          <Link to="/patients" className="patient-profile-link">
            Full Patient Record <ArrowRight size={14} />
          </Link>
        </div>
      </section>

      {/* Backend connection warning if needed */}
      {data.error && (
        <div className="notice">
          <strong>Notice:</strong> {data.error}. Displaying cached or demo values until connection is restored.
        </div>
      )}

      {/* AI Exacerbation Risk Prediction Panel */}
      <RiskCard prediction={data.prediction} loading={data.loading} />

      {/* Sensor Biomarker Snapshot Section */}
      <section className="section-heading">
        <div>
          <span className="eyebrow">PHYSIOLOGICAL TELEMETRY</span>
          <h2>Sensor Snapshot (8 Multi-Modal Indices)</h2>
          <p className="section-subtext">Continuous wearable metrics from TOLIFE clinical health dataset</p>
        </div>
        <Link to="/monitoring" className="section-action-link">
          Explore Trend Analytics <ArrowRight size={15} />
        </Link>
      </section>

      {/* 8 Sensor Cards Grid */}
      <div className="sensor-grid">
        {data.measures.length ? (
          data.measures.map((m) => (
            <SensorCard measurement={m} key={m.id || `${m.sensor_type}-${m.measured_at}`} />
          ))
        ) : (
          <EmptyState title="No recent sensor measurements available" />
        )}
      </div>

      {/* Bottom Row: Alerts Feed + Clinical Guidelines */}
      <section className="two-column">
        {/* Left: Recent Alerts */}
        <div className="card alerts-feed-card">
          <div className="card-header-clean">
            <div>
              <span className="eyebrow">TRIAGE QUEUE</span>
              <h2>Active Clinical Alerts</h2>
            </div>
            <Link to="/alerts" className="view-all-link">
              View all ({data.alerts.length})
            </Link>
          </div>

          <div className="alerts-feed-list">
            {data.alerts.slice(0, 3).length ? (
              data.alerts.slice(0, 3).map((a) => (
                <div className="compact-alert-item" key={a.id}>
                  <div className={`alert-severity-indicator ${String(a.alert_level).toLowerCase()}`}>
                    <BellRing size={15} />
                  </div>
                  <div className="alert-content">
                    <div className="alert-top-line">
                      <strong>{a.alert_level || 'Risk'} Severity Alert</strong>
                      <span className="alert-time">{formatDate(a.created_at)}</span>
                    </div>
                    <p>{a.message || 'Respiratory biomarker variation detected by exacerbation model.'}</p>
                  </div>
                </div>
              ))
            ) : (
              <p className="no-alerts-msg">
                <CheckCircle2 size={16} /> All biomarkers within tolerated COPD baseline. No pending alerts.
              </p>
            )}
          </div>
        </div>

        {/* Right: Decision Support / GOLD Protocol */}
        <div className="card clinical-protocol-card">
          <div className="card-header-clean">
            <div>
              <span className="eyebrow">GOLD CLINICAL GUIDELINES</span>
              <h2>Decision Support Rules</h2>
            </div>
            <ShieldCheck size={20} className="protocol-shield-icon" />
          </div>

          <div className="protocol-body">
            <div className="protocol-rule">
              <strong>Acute Deterioration Trigger:</strong>
              <p>If resting SpO₂ drops below 90% or breathing rate exceeds 24 bpm for &gt;2 consecutive observations, initiate phone triage.</p>
            </div>

            <div className="protocol-rule">
              <strong>Intervention Checklist:</strong>
              <ul>
                <li>Confirm maintenance inhaler / bronchodilator adherence</li>
                <li>Evaluate nocturnal coughing (SII) spike patterns</li>
                <li>Review 7-day predicted exacerbation probability trajectory</li>
              </ul>
            </div>

            <div className="protocol-disclaimer">
              <small>
                ExacerbAlert is a research clinical decision support tool developed under TechSeva. It assists healthcare professionals and does not replace emergency clinical judgment.
              </small>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
