import { useEffect, useState } from 'react'
import EmptyState from '../components/EmptyState'
import { formatDate } from '../components/RiskCard'
import { getPredictionHistory } from '../services/api'

export default function Predictions({ selectedPatient }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!selectedPatient?.id) return

    let isSubscribed = true
    setLoading(true)
    setError('')

    getPredictionHistory(selectedPatient.id)
      .then((records) => {
        if (isSubscribed) {
          setItems(records)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (isSubscribed) {
          setItems([])
          setError(err.message)
          setLoading(false)
        }
      })

    return () => {
      isSubscribed = false
    }
  }, [selectedPatient?.id])

  if (!selectedPatient) {
    return (
      <EmptyState
        title="No participant selected"
        detail="Select a participant from the selector to view prediction history."
      />
    )
  }

  const participantLabel = selectedPatient.participant_id || selectedPatient.patient_id || `ID ${selectedPatient.id}`

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">ML RISK FORECASTING</p>
          <h2>Prediction history</h2>
          <p>Model outputs and exacerbation risk assessments for {participantLabel}.</p>
        </div>
        <div className="monitoring-live">
          <span />
          <span>{loading ? 'Fetching predictions...' : 'ML pipeline connected'}</span>
        </div>
      </div>

      {error ? (
        <EmptyState title="Prediction history unavailable" detail={error} />
      ) : items.length ? (
        <div className="table-wrap card">
          <table>
            <thead>
              <tr>
                <th>Generated</th>
                <th>Exacerbation Risk</th>
                <th>Category</th>
                <th>Forecast Horizon</th>
                <th>Model Version</th>
              </tr>
            </thead>
            <tbody>
              {items.map((p) => {
                const prob = typeof p.risk_probability === 'number' ? Math.round(p.risk_probability * 100) : null
                const category = p.risk_level ? String(p.risk_level).toLowerCase() : 'neutral'
                return (
                  <tr key={p.id}>
                    <td>{formatDate(p.prediction_timestamp || p.created_at)}</td>
                    <td>
                      <strong>{prob !== null ? `${prob}%` : '—'}</strong>
                    </td>
                    <td>
                      <span className={`badge ${category}`}>{p.risk_level || '—'}</span>
                    </td>
                    <td>{p.prediction_horizon_days ? `${p.prediction_horizon_days} days` : '—'}</td>
                    <td><code>{p.model_version || '—'}</code></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="Awaiting prediction outputs"
          detail="No forward exacerbation risk predictions have been generated for this participant. Predictions will appear here once the Phase 3 ML forecasting pipeline generates verified scores."
        />
      )}

      <p className="page-note">
        All risk probabilities and categories are calculated by validated backend ML models. The frontend never computes or estimates risk scores.
      </p>
    </div>
  )
}
