import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Cpu,
  Info,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react'
import EmptyState from '../components/EmptyState'
import { formatDate } from '../components/RiskCard'
import { getPredictionHistory } from '../services/api'

export default function Predictions({ selectedPatient }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const patientId = selectedPatient?.participant_id || selectedPatient?.patient_id || `DEMO-00${selectedPatient?.id || 1}`

  useEffect(() => {
    if (selectedPatient?.id) {
      setLoading(true)
      getPredictionHistory(selectedPatient.id)
        .then((data) => {
          setItems(data)
          setLoading(false)
        })
        .catch((e) => {
          setError(e.message)
          setLoading(false)
        })
    }
  }, [selectedPatient?.id])

  if (!selectedPatient) return <EmptyState title="No participant selected" detail="Select a participant to view ML exacerbation forecast history." />

  const latestPred = items[0]
  const latestProb = latestPred ? Math.round((latestPred.risk_probability ?? 0) * 100) : null
  const latestLevel = latestPred?.risk_level || 'LOW'

  return (
    <div className="page predictions-page">
      {/* Unified Professional Page Header */}
      <div className="page-header-bar">
        <div className="page-header-content">
          <div className="page-header-pre">
            <span>PREDICTIVE INTELLIGENCE</span>
            <span className="page-header-sep">/</span>
            <span className="page-header-patient">{patientId}</span>
          </div>
          <div className="page-header-title-row">
            <h2>Exacerbation Prediction History</h2>
            <span className="page-header-badge">TOLIFE ML Engine</span>
          </div>
          <p className="page-header-desc">
            Historical audit log of longitudinal COPD exacerbation risk probabilities, forecast windows, and model version releases.
          </p>
        </div>

        <div className="page-header-actions">
          <div className="monitoring-status-beacon">
            <span className="beacon-dot" />
            <div className="beacon-text">
              <small>MODEL STATUS</small>
              <strong>TOLIFE Ensemble v1.4</strong>
            </div>
          </div>
        </div>
      </div>

      {/* Summary KPI Strip */}
      <div className="predictions-summary-strip">
        <div className="card summary-kpi-card">
          <span className="eyebrow">CURRENT EVALUATION</span>
          <div className="kpi-val-row">
            <strong>{latestProb !== null ? `${latestProb}%` : '—'}</strong>
            <span className={`risk-pill ${String(latestLevel).toLowerCase()}`}>
              {latestLevel} RISK
            </span>
          </div>
          <small>Computed from latest wearable window</small>
        </div>

        <div className="card summary-kpi-card">
          <span className="eyebrow">PREDICTION HORIZON</span>
          <div className="kpi-val-row">
            <strong>{latestPred?.prediction_horizon_days ?? 7} Days</strong>
            <CalendarClock size={16} className="text-teal" />
          </div>
          <small>Advance clinical triage window</small>
        </div>

        <div className="card summary-kpi-card">
          <span className="eyebrow">AUDIT EPOCHS</span>
          <div className="kpi-val-row">
            <strong>{items.length} Runs</strong>
            <Cpu size={16} className="text-teal" />
          </div>
          <small>Validated inference cycles</small>
        </div>
      </div>

      {/* Table Section */}
      {error ? (
        <EmptyState title="Prediction history unavailable" detail={error} />
      ) : loading ? (
        <div className="card skeleton-block" style={{ height: '220px', borderRadius: '12px' }} />
      ) : items.length ? (
        <div className="table-wrap card">
          <table>
            <thead>
              <tr>
                <th>Generated Timestamp</th>
                <th>Exacerbation Probability</th>
                <th>Risk Category</th>
                <th>Forecast Horizon</th>
                <th>Model Architecture</th>
                <th>Clinical Recommendation</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => {
                const prob = Math.round((p.risk_probability ?? 0) * 100)
                const lvl = String(p.risk_level || 'LOW').toUpperCase()
                return (
                  <tr key={p.id}>
                    <td>
                      <strong>{formatDate(p.prediction_timestamp || p.created_at)}</strong>
                    </td>
                    <td>
                      <div className="table-prob-cell">
                        <strong>{prob}%</strong>
                        <div className="table-prob-track">
                          <div
                            className={`table-prob-fill ${lvl.toLowerCase()}`}
                            style={{ width: `${Math.min(prob, 100)}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className={`badge ${lvl.toLowerCase()}`}>{lvl}</span>
                    </td>
                    <td>
                      <span>{p.prediction_horizon_days ?? 7} Days Ahead</span>
                    </td>
                    <td>
                      <code>{p.model_version || 'XGBoost-Ensemble-v1.4'}</code>
                    </td>
                    <td>
                      <span className="table-rec-text">
                        {lvl === 'HIGH'
                          ? 'Urgent phone triage recommended'
                          : lvl === 'MEDIUM'
                          ? 'Review inhaler adherence & SpO₂'
                          : 'Routine telemetry surveillance'}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No prediction history recorded"
          detail="Predictions will populate automatically as the backend executes the approved model pipeline on incoming sensor telemetry."
        />
      )}

      <p className="page-note">
        All model outputs are non-diagnostic statistical estimations calculated according to the TOLIFE research protocol.
      </p>
    </div>
  )
}
