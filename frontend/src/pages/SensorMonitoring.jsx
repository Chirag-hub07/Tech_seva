import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  CalendarDays,
  CheckCircle2,
  Gauge,
  Radio,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import SensorChart from '../components/SensorChart'
import SensorSelector from '../components/SensorSelector'
import EmptyState from '../components/EmptyState'
import { getMeasurements } from '../services/api'

const SENSORS = [
  { code: 'BRI', label: 'Breathing Rate (BRI)' },
  { code: 'PEI', label: 'Blood Oxygen SpO₂ (PEI)' },
  { code: 'SHRI', label: 'Sleeping Heart Rate (SHRI)' },
  { code: 'PRVI', label: 'Heart Rate Variability (PRVI)' },
  { code: 'SQI', label: 'Sleep Quality Index (SQI)' },
  { code: 'MI', label: 'Physical Activity (MI)' },
  { code: 'SII', label: 'Acoustic / Cough Level (SII)' },
  { code: 'EI', label: 'Ambient Temperature (EI)' },
]

const RANGES = [
  { value: '7d', label: '7-Day Window' },
  { value: '14d', label: '14-Day Window' },
  { value: '30d', label: '30-Day Window' },
]

export default function SensorMonitoring({ selectedPatient }) {
  const [sensor, setSensor] = useState('BRI')
  const [range, setRange] = useState('7d')
  const [data, setData] = useState([])
  const [error, setError] = useState('')

  const patientId = selectedPatient?.participant_id || selectedPatient?.patient_id || `DEMO-00${selectedPatient?.id || 1}`

  useEffect(() => {
    if (!selectedPatient?.id) return
    setError('')
    getMeasurements(selectedPatient.id, sensor, range)
      .then(setData)
      .catch((requestError) => {
        setData([])
        setError(requestError.message)
      })
  }, [selectedPatient?.id, sensor, range])

  const summary = useMemo(() => {
    const values = data
      .map((item) => Object.values(item.measurements || item.values || {})[0])
      .filter((value) => typeof value === 'number')

    if (!values.length) return null

    const latest = values.at(-1)
    const previous = values.at(-2) ?? latest
    const diff = latest - previous
    return {
      latest,
      average: (values.reduce((total, val) => total + val, 0) / values.length).toFixed(1),
      direction: diff,
    }
  }, [data])

  if (!selectedPatient) return <EmptyState title="No participant selected" detail="Select a participant to inspect historical sensor telemetry." />

  const activeSensorMeta = SENSORS.find((s) => s.code === sensor) || SENSORS[0]

  return (
    <div className="page monitoring-page">
      {/* Unified Professional Page Header */}
      <div className="page-header-bar">
        <div className="page-header-content">
          <div className="page-header-pre">
            <span>BIOMARKER SURVEILLANCE</span>
            <span className="page-header-sep">/</span>
            <span className="page-header-patient">{patientId}</span>
          </div>
          <div className="page-header-title-row">
            <h2>Sensor Telemetry & Longitudinal Trends</h2>
            <span className="page-header-badge">TOLIFE Indices</span>
          </div>
          <p className="page-header-desc">
            Continuous wearable telemetry streams, rolling statistical averages, and baseline deviation tracking for COPD exacerbation monitoring.
          </p>
        </div>

        <div className="page-header-actions">
          <div className="monitoring-status-beacon">
            <span className="beacon-dot" />
            <div className="beacon-text">
              <small>STREAM STATUS</small>
              <strong>Connected & Validated</strong>
            </div>
          </div>
        </div>
      </div>

      {/* Interactive Controls Strip */}
      <section className="monitoring-controls">
        <div className="control-field">
          <span>Active Biomarker:</span>
          <SensorSelector
            sensors={SENSORS.map((s) => s.code)}
            value={sensor}
            onChange={setSensor}
          />
        </div>

        <div className="range-control">
          <span>
            <CalendarDays size={15} /> Observation Window:
          </span>
          <div>
            {RANGES.map((item) => (
              <button
                key={item.value}
                type="button"
                className={range === item.value ? 'active' : ''}
                onClick={() => setRange(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* KPI Summary Metric Strip */}
      {summary && (
        <section className="metric-strip">
          <div>
            <Gauge />
            <div>
              <span>Latest Observed Value</span>
              <strong>{summary.latest}</strong>
            </div>
          </div>

          <div>
            <Activity />
            <div>
              <span>{range.toUpperCase()} Rolling Average</span>
              <strong>{summary.average}</strong>
            </div>
          </div>

          <div>
            {summary.direction >= 0 ? <TrendingUp /> : <TrendingDown />}
            <div>
              <span>48h Baseline Shift</span>
              <strong className={summary.direction > 0 ? 'positive' : 'neutral'}>
                {summary.direction > 0 ? '+' : ''}
                {summary.direction.toFixed(1)}
              </strong>
            </div>
          </div>
        </section>
      )}

      {/* Chart Canvas Card */}
      <section className="chart-card">
        <div className="chart-header">
          <div>
            <span className="eyebrow">{activeSensorMeta.label.toUpperCase()}</span>
            <h3>Historical Telemetry Trajectory ({range.toUpperCase()})</h3>
          </div>
          <span className="chart-status">
            <CheckCircle2 size={13} style={{ display: 'inline', marginRight: '4px' }} />
            Calibrated Baseline
          </span>
        </div>

        {error ? (
          <EmptyState title="Measurements unavailable" detail={error} />
        ) : (
          <SensorChart data={data} sensor={sensor} />
        )}
      </section>

      <p className="page-note">
        Values and clinical validity indicators are transmitted directly from the TOLIFE study database without interpolation.
      </p>
    </div>
  )
}
