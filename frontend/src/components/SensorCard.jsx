import { Activity } from 'lucide-react'
export default function SensorCard({ measurement }) {
  const values = measurement.measurements || measurement.values || {}
  const [name, value] = Object.entries(values)[0] || ['Measurement', measurement.value]
  return <article className="sensor-card card"><div className="sensor-icon"><Activity size={19} /></div><div><p>{measurement.sensor_type || 'Sensor'}</p><strong>{value ?? '—'}</strong><small>{name.replaceAll('_', ' ')}</small></div><span className={measurement.is_valid === false ? 'invalid' : 'valid'}>{measurement.is_valid === false ? 'Check' : 'Valid'}</span></article>
}
