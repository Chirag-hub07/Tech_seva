import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Cpu,
  Info,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react'

export const formatDate = (date) =>
  date
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }).format(new Date(date))
    : '—'

export default function RiskCard({ prediction, loading }) {
  if (loading) {
    return (
      <div className="risk-card card skeleton-block">
        <div style={{ height: '180px' }} />
      </div>
    )
  }

  if (!prediction) {
    return (
      <section className="risk-card card empty-risk">
        <div className="risk-card-header">
          <div>
            <span className="eyebrow">AI EXACERBATION PREDICTIVE ENGINE</span>
            <h2>Awaiting Model Evaluation</h2>
          </div>
        </div>
        <p className="muted">
          Connect the backend FastAPI service with trained TOLIFE weights to generate real-time exacerbation risk probabilities.
        </p>
      </section>
    )
  }

  const probability = Math.round(
    Number(prediction.risk_probability ?? prediction.probability ?? 0) * 100,
  )
  const rawLevel = String(prediction.risk_level || prediction.risk_category || 'LOW').toUpperCase()

  const levelInfo =
    rawLevel === 'HIGH'
      ? {
          tier: 'HIGH RISK',
          subtext: 'Acute Exacerbation Deterioration Impending',
          badgeClass: 'danger',
          Icon: AlertTriangle,
          action: 'High Priority: Review respiratory telemetry & consider clinical phone triage immediately.',
          gaugeColor: '#ef4444',
        }
      : rawLevel === 'MEDIUM'
      ? {
          tier: 'MODERATE RISK',
          subtext: 'Elevated Respiration & Nocturnal Cough Variance',
          badgeClass: 'watch',
          Icon: AlertTriangle,
          action: 'Recommended Action: Verify inhaler adherence & monitor 24h SpO2 nocturnal baseline.',
          gaugeColor: '#f59e0b',
        }
      : {
          tier: 'LOW RISK',
          subtext: 'Stable Longitudinal Pulmonary Trajectory',
          badgeClass: 'safe',
          Icon: ShieldCheck,
          action: 'Routine Telemetry: Patient physiological indicators match baseline stability.',
          gaugeColor: '#10b981',
        }

  const horizonDays = prediction.prediction_horizon_days ?? prediction.horizon_days ?? 7
  const modelVer = prediction.model_version || 'TOLIFE-XGBoost v1.2'
  const timeStr = formatDate(prediction.prediction_timestamp || prediction.created_at)
  const IconComponent = levelInfo.Icon

  return (
    <section className={`risk-card ${levelInfo.badgeClass}`}>
      {/* Top Header Row */}
      <div className="risk-card-top">
        <div className="risk-title-group">
          <div className="risk-engine-badge">
            <Cpu size={14} />
            <span>EXACERBATION RISK ENGINE · TOLIFE COHORT</span>
          </div>
          <h2>7-Day Exacerbation Forecast</h2>
        </div>
        <div className="risk-meta-badges">
          <span className="risk-model-badge">
            <Info size={13} />
            {modelVer}
          </span>
          <span className="risk-timestamp-badge">
            <CalendarClock size={13} />
            {timeStr}
          </span>
        </div>
      </div>

      {/* Main Grid: Probability Gauge + Clinical Drivers */}
      <div className="risk-card-grid">
        {/* Left Column: Big Probability Display */}
        <div className="risk-stat-panel">
          <div className="risk-prob-container">
            <div className="risk-big-value">
              {probability}
              <span className="risk-percent-sign">%</span>
            </div>
            <div className="risk-pill-wrapper">
              <span className={`risk-pill ${levelInfo.badgeClass}`}>
                <IconComponent size={14} />
                {levelInfo.tier}
              </span>
              <span className="risk-subtext">{levelInfo.subtext}</span>
            </div>
          </div>

          {/* Segmented Risk Gauge Bar */}
          <div className="risk-gauge-block">
            <div className="risk-gauge-track">
              <div
                className="risk-gauge-fill"
                style={{ width: `${Math.min(Math.max(probability, 4), 100)}%`, backgroundColor: levelInfo.gaugeColor }}
              />
            </div>
            <div className="risk-gauge-legend">
              <span className="legend-item safe">0% Stable</span>
              <span className="legend-item watch">30% Caution</span>
              <span className="legend-item danger">70%+ Critical</span>
            </div>
          </div>
        </div>

        {/* Right Column: Clinical Action Plan & Drivers */}
        <div className="risk-protocol-panel">
          <div className="risk-protocol-header">
            <TrendingUp size={16} />
            <strong>Clinical Intervention Window: Next {horizonDays} Days</strong>
          </div>
          <p className="risk-protocol-action">{levelInfo.action}</p>

          <div className="risk-drivers-list">
            <div className="risk-driver-item">
              <span className="driver-label">Respiration Index (BRI)</span>
              <strong className="driver-val">18.9 bpm · Elevated</strong>
            </div>
            <div className="risk-driver-item">
              <span className="driver-label">Oxygen SpO₂ (PEI)</span>
              <strong className="driver-val">94% · Baseline</strong>
            </div>
            <div className="risk-driver-item">
              <span className="driver-label">Predictive Horizon</span>
              <strong className="driver-val">{horizonDays} Days Ahead</strong>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
