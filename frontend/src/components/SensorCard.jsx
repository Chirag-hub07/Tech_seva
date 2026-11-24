import {
  Activity,
  CheckCircle2,
  Heart,
  HeartPulse,
  Moon,
  Thermometer,
  Volume2,
  Wind,
  Zap,
} from 'lucide-react'

const SENSOR_META = {
  BRI: {
    title: 'Breathing Rate',
    category: 'Respiratory',
    unit: 'bpm',
    normal: '12 – 20 bpm',
    Icon: Wind,
    accent: '#0d9488',
  },
  PEI: {
    title: 'Blood Oxygen (SpO₂)',
    category: 'Pulmonary',
    unit: '%',
    normal: '92 – 96%',
    Icon: Activity,
    accent: '#06b6d4',
  },
  SHRI: {
    title: 'Sleeping Heart Rate',
    category: 'Cardiovascular',
    unit: 'bpm',
    normal: '55 – 75 bpm',
    Icon: HeartPulse,
    accent: '#f43f5e',
  },
  PRVI: {
    title: 'Heart Rate Variability',
    category: 'Autonomic',
    unit: 'ms',
    normal: '30 – 65 ms',
    Icon: Heart,
    accent: '#8b5cf6',
  },
  EI: {
    title: 'Ambient Temperature',
    category: 'Environment',
    unit: '°C',
    normal: '20 – 24 °C',
    Icon: Thermometer,
    accent: '#f59e0b',
  },
  SQI: {
    title: 'Sleep Quality Index',
    category: 'Sleep Health',
    unit: 'pts',
    normal: '70 – 100',
    Icon: Moon,
    accent: '#3b82f6',
  },
  MI: {
    title: 'Physical Mobility',
    category: 'Activity',
    unit: 'score',
    normal: '50 – 100',
    Icon: Zap,
    accent: '#10b981',
  },
  SII: {
    title: 'Acoustic / Cough Index',
    category: 'Symptoms',
    unit: 'dB',
    normal: '< 40 dB',
    Icon: Volume2,
    accent: '#6366f1',
  },
}

export default function SensorCard({ measurement }) {
  const code = (measurement.sensor_type || 'BRI').toUpperCase()
  const meta = SENSOR_META[code] || {
    title: code,
    category: 'Biomarker',
    unit: '',
    normal: 'Active',
    Icon: Activity,
    accent: '#0d9488',
  }

  const values = measurement.measurements || measurement.values || {}
  const rawValue = Object.values(values)[0] ?? measurement.value
  const displayVal = typeof rawValue === 'number' ? rawValue : '—'
  const isValid = measurement.is_valid !== false
  const IconComponent = meta.Icon

  return (
    <article className="sensor-card">
      <div className="sensor-card-top">
        <div className="sensor-card-badge" style={{ color: meta.accent, backgroundColor: `${meta.accent}14` }}>
          <IconComponent size={16} />
          <span>{code}</span>
        </div>
        <span className={`sensor-status-chip ${isValid ? 'valid' : 'invalid'}`}>
          {isValid ? 'Valid Telemetry' : 'Check Sensor'}
        </span>
      </div>

      <div className="sensor-card-body">
        <h3 className="sensor-card-title">{meta.title}</h3>
        <p className="sensor-card-cat">{meta.category}</p>
        <div className="sensor-card-val-row">
          <span className="sensor-card-val">{displayVal}</span>
          <span className="sensor-card-unit">{meta.unit}</span>
        </div>
      </div>

      <div className="sensor-card-footer">
        <span className="sensor-normal-range">Normal: {meta.normal}</span>
        <CheckCircle2 size={13} className={isValid ? 'check-green' : 'check-gray'} />
      </div>
    </article>
  )
}
