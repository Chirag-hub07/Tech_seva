import { AlertTriangle, BellRing, Check, CheckCircle2, Clock } from 'lucide-react'
import { formatDate } from './RiskCard'

export default function AlertCard({ alert, onAcknowledge }) {
  const status = String(alert.status || 'pending').toLowerCase()
  const isPending = status === 'pending'
  const level = String(alert.alert_level || 'MEDIUM').toUpperCase()

  return (
    <article className={`alert-card ${status} level-${level.toLowerCase()}`}>
      <div className={`alert-icon-box ${level.toLowerCase()}`}>
        {level === 'HIGH' ? <AlertTriangle size={18} /> : <BellRing size={18} />}
      </div>

      <div className="alert-body">
        <div className="alert-meta-line">
          <div className="alert-tags-group">
            <span className={`badge ${level.toLowerCase()}`}>{level} SEVERITY</span>
            <span className={`alert-status-pill ${isPending ? 'pending' : 'resolved'}`}>
              {isPending ? 'Action Required' : 'Acknowledged'}
            </span>
          </div>
          <span className="alert-timestamp">
            <Clock size={12} />
            {formatDate(alert.created_at)}
          </span>
        </div>

        <p className="alert-message-text">{alert.message || 'Respiratory telemetry variance detected.'}</p>
        <small className="alert-source-subtext">Trigger: Exacerbation Early Warning Rule Engine</small>
      </div>

      {isPending && (
        <button
          type="button"
          className="alert-ack-btn"
          onClick={() => onAcknowledge(alert.id)}
          title="Acknowledge and mark reviewed"
        >
          <Check size={15} />
          <span>Acknowledge</span>
        </button>
      )}
    </article>
  )
}
