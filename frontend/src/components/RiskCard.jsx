import { AlertTriangle, CalendarClock, ShieldCheck } from 'lucide-react'
const tone = (level) => ({ LOW: 'safe', MEDIUM: 'watch', HIGH: 'danger' }[String(level).toUpperCase()] || 'neutral')
export default function RiskCard({ prediction, loading }) {
  if (loading) return <div className="risk-card card skeleton-block" />
  if (!prediction) return <div className="risk-card card"><p className="eyebrow">CURRENT EXACERBATION RISK</p><h2>Awaiting prediction</h2><p className="muted">The backend has not returned a prediction for this patient.</p></div>
  const probability = Number(prediction.risk_probability ?? prediction.probability ?? 0)
  const level = prediction.risk_level || prediction.risk_category || 'Unknown'
  const icon = String(level).toUpperCase() === 'HIGH' ? <AlertTriangle /> : <ShieldCheck />
  return <section className={`risk-card card ${tone(level)}`}><div><p className="eyebrow">CURRENT EXACERBATION RISK</p><div className="risk-value">{Math.round(probability * 100)}<span>%</span></div><span className="risk-pill">{level}</span></div>
    <div className="risk-meta"><div>{icon}<span>Risk category</span><strong>{level}</strong></div><div><CalendarClock /><span>Prediction horizon</span><strong>{prediction.prediction_horizon_days ?? prediction.horizon_days ?? '—'} days</strong></div><p>Generated {formatDate(prediction.prediction_timestamp || prediction.created_at)}</p></div></section>
}
export const formatDate = (date) => date ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(date)) : '—'
