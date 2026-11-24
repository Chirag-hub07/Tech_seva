import { AlertTriangle, CalendarClock, ShieldCheck } from 'lucide-react'

const tone = (level) => ({ LOW: 'safe', MEDIUM: 'watch', HIGH: 'danger' }[String(level).toUpperCase()] || 'neutral')

export default function RiskCard({ prediction, loading }) {
  if (loading) {
    return <div className="risk-card card skeleton-block" />
  }

  if (!prediction) {
    return (
      <div className="risk-card card">
        <div>
          <p className="eyebrow">CURRENT EXACERBATION RISK</p>
          <h2>Awaiting prediction</h2>
          <p className="muted">
            No forward risk calculation is recorded for this participant. Awaiting backend ML pipeline output.
          </p>
        </div>
      </div>
    )
  }

  const rawProb = prediction.risk_probability ?? prediction.probability
  const hasProbability = typeof rawProb === 'number' && Number.isFinite(rawProb)
  const probabilityPercent = hasProbability ? Math.round(rawProb * 100) : null

  const level = prediction.risk_level || prediction.risk_category || 'Unrated'
  const icon = String(level).toUpperCase() === 'HIGH' ? <AlertTriangle /> : <ShieldCheck />
  const horizon = prediction.prediction_horizon_days ?? prediction.horizon_days

  return (
    <section className={`risk-card card ${tone(level)}`}>
      <div>
        <p className="eyebrow">CURRENT EXACERBATION RISK</p>
        <div className="risk-value">
          {probabilityPercent !== null ? probabilityPercent : '—'}
          {probabilityPercent !== null && <span>%</span>}
        </div>
        <span className="risk-pill">{level}</span>
      </div>

      <div className="risk-meta">
        <div>
          {icon}
          <span>Risk category</span>
          <strong>{level}</strong>
        </div>
        <div>
          <CalendarClock />
          <span>Prediction horizon</span>
          <strong>{horizon ? `${horizon} days` : 'Not specified'}</strong>
        </div>
        <p>Generated {formatDate(prediction.prediction_timestamp || prediction.created_at)}</p>
      </div>
    </section>
  )
}

export const formatDate = (date) =>
  date
    ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(date))
    : '—'
