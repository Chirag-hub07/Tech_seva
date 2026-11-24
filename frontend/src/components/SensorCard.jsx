import { Activity } from 'lucide-react'
import { extractPrimaryMetric } from '../utils/sensorMetrics'

export default function SensorCard({ measurement }) {
  const metric = extractPrimaryMetric(measurement)

  // Clinical validity presentation:
  // is_valid === true: 'Valid' (verified quality)
  // is_valid === false: 'Invalid' (flagged reading)
  // is_valid === null: 'Unverified' (raw / unassessed)
  let validityClass = 'unverified'
  let validityLabel = 'Unverified'
  if (metric.isValid === true) {
    validityClass = 'valid'
    validityLabel = 'Valid'
  } else if (metric.isValid === false) {
    validityClass = 'invalid'
    validityLabel = 'Invalid'
  }

  return (
    <article className="sensor-card card">
      <div className="sensor-icon">
        <Activity size={19} />
      </div>
      <div>
        <p>{measurement.sensor_type || 'Sensor'}</p>
        <strong className={metric.isValid === false ? 'invalid-reading' : ''}>
          {metric.isValid === false ? (
            <span title="Invalid sensor reading flagged by QC checks">{metric.formattedValue}*</span>
          ) : (
            metric.formattedValue
          )}
        </strong>
        <small title={metric.label}>{metric.label}</small>
      </div>
      <span className={validityClass} title={`Quality status: ${validityLabel}`}>
        {validityLabel}
      </span>
    </article>
  )
}
