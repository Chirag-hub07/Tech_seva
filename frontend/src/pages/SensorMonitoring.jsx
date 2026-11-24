import { useEffect, useMemo, useState } from 'react'
import { Activity, CalendarDays, Gauge, TrendingUp } from 'lucide-react'
import SensorChart from '../components/SensorChart'
import SensorSelector from '../components/SensorSelector'
import EmptyState from '../components/EmptyState'
import { getMeasurements } from '../services/api'
import { getChartNumericKey, SENSOR_DEFINITIONS } from '../utils/sensorMetrics'

const sensors = ['BRI', 'EI', 'MI', 'PEI', 'PRVI', 'SHRI', 'SII', 'SQI']

const ranges = [
  { value: '7d', label: '7 days' },
  { value: '14d', label: '14 days' },
  { value: '30d', label: '30 days' },
  { value: '60d', label: '60 days' },
  { value: '90d', label: '90 days' },
  { value: 'all', label: 'All available' },
]

export default function SensorMonitoring({ selectedPatient }) {
  const [sensor, setSensor] = useState('BRI')
  const [range, setRange] = useState('7d')
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!selectedPatient?.id) return
    let isSubscribed = true
    setError('')
    setLoading(true)

    getMeasurements(selectedPatient.id, sensor, range)
      .then((records) => {
        if (isSubscribed) {
          setData(records)
          setLoading(false)
        }
      })
      .catch((requestError) => {
        if (isSubscribed) {
          setData([])
          setError(requestError.message)
          setLoading(false)
        }
      })

    return () => {
      isSubscribed = false
    }
  }, [selectedPatient?.id, sensor, range])

  const targetKey = useMemo(() => getChartNumericKey(data, sensor), [data, sensor])

  const summary = useMemo(() => {
    if (!data.length || !targetKey) return null

    const validValues = data
      .map((item) => {
        const metrics = item.measurements || item.values || {}
        return metrics[targetKey]
      })
      .filter((val) => typeof val === 'number')

    if (!validValues.length) return null

    const latest = validValues.at(-1)
    const previous = validValues.at(-2) ?? latest
    const avg = validValues.reduce((tot, v) => tot + v, 0) / validValues.length

    return {
      latest: Number.isInteger(latest) ? latest : latest.toFixed(1),
      average: avg.toFixed(1),
      direction: latest - previous,
    }
  }, [data, targetKey])

  const latestDate = useMemo(() => {
    if (!data.length) return null
    return new Date(data.at(-1).measured_at).toLocaleDateString(undefined, {
      dateStyle: 'medium',
    })
  }, [data])

  const sensorName = SENSOR_DEFINITIONS[sensor]?.shortName || sensor
  const rangeConfig = ranges.find((r) => r.value === range)
  const rangeTitle = range === 'all' ? 'FULL LONGITUDINAL' : `${rangeConfig?.label?.toUpperCase()} RECORDED`

  if (!selectedPatient) return <EmptyState title="No patient selected" detail="Select a participant to view telemetry." />

  return (
    <div className="page monitoring-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">HISTORICAL TELEMETRY</p>
          <h2>Sensor monitoring</h2>
          <p>Longitudinal sensor observations for participant {selectedPatient.participant_id || `ID ${selectedPatient.id}`}.</p>
        </div>
        <div className="monitoring-live">
          <span />
          <span>{loading ? 'Fetching series...' : 'Stream connected'}</span>
        </div>
      </div>

      <section className="monitoring-controls card">
        <div className="control-field">
          <span>Sensor stream</span>
          <SensorSelector sensors={sensors} value={sensor} onChange={setSensor} />
        </div>
        <div className="range-control">
          <span>
            <CalendarDays size={16} /> Time window
          </span>
          <div>
            {ranges.map((item) => (
              <button
                key={item.value}
                className={range === item.value ? 'active' : ''}
                onClick={() => setRange(item.value)}
              >
                {item.value === 'all' ? 'All records' : `Prior ${item.label}`}
              </button>
            ))}
          </div>
        </div>
      </section>

      {summary && (
        <section className="metric-strip">
          <div>
            <Gauge />
            <span>Latest recorded</span>
            <strong>{summary.latest}</strong>
          </div>
          <div>
            <Activity />
            <span>Period average</span>
            <strong>{summary.average}</strong>
          </div>
          <div>
            <TrendingUp />
            <span>Window trend</span>
            <strong className={summary.direction > 0 ? 'positive' : 'neutral'}>
              {summary.direction > 0 ? '+' : ''}
              {summary.direction.toFixed(1)}
            </strong>
          </div>
        </section>
      )}

      <section className="card chart-card">
        <div className="chart-header">
          <div>
            <p className="eyebrow">{rangeTitle} HISTORY</p>
            <h3>{sensorName} trend</h3>
          </div>
          <span className="chart-status">
            {latestDate ? `Anchored to ${latestDate}` : 'Database connected'}
          </span>
        </div>
        {error ? (
          <EmptyState title="Telemetry unavailable" detail={error} />
        ) : (
          <SensorChart data={data} sensor={sensor} />
        )}
      </section>

      <p className="page-note">
        Historical time windows are anchored to the participant&apos;s latest recorded measurement
        {latestDate ? ` (${latestDate})` : ''}, not today&apos;s date. Invalid and unverified observations are tagged.
      </p>
    </div>
  )
}
