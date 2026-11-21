import { useEffect, useState } from 'react'
import { ArrowRight, BellRing, Radio } from 'lucide-react'
import { Link } from 'react-router-dom'
import RiskCard, { formatDate } from '../components/RiskCard'
import SensorCard from '../components/SensorCard'
import EmptyState from '../components/EmptyState'
import { getAlerts, getLatestMeasurements, getLatestPrediction } from '../services/api'
export default function Dashboard({ selectedPatient, patientError }) {
  const [data, setData] = useState({ prediction: null, measures: [], alerts: [], loading: false, error: '' })
  useEffect(() => { if (!selectedPatient?.id) return; setData((d) => ({ ...d, loading: true, error: '' })); Promise.all([getLatestPrediction(selectedPatient.id), getLatestMeasurements(selectedPatient.id), getAlerts(selectedPatient.id)]).then(([prediction, measures, alerts]) => setData({ prediction, measures, alerts, loading: false, error: '' })).catch((e) => setData({ prediction: null, measures: [], alerts: [], loading: false, error: e.message })) }, [selectedPatient?.id])
  if (!selectedPatient) return <EmptyState title="Connect the backend to begin" detail={patientError || 'Set VITE_API_BASE_URL and ensure the FastAPI service is running.'} />
  return <div className="page"><section className="patient-banner"><div><p className="eyebrow">ACTIVE PATIENT</p><h2>{selectedPatient.participant_id || selectedPatient.patient_id || `Patient ${selectedPatient.id}`}</h2><span>{selectedPatient.country || 'Country not recorded'}</span></div><div className="monitoring-state"><Radio /><span>Monitoring status</span><strong>{selectedPatient.monitoring_status || 'Active'}</strong></div></section>
    {data.error && <div className="notice">{data.error} Showing no clinical data until the connection is restored.</div>}
    <RiskCard prediction={data.prediction} loading={data.loading} />
    <section className="section-heading"><div><p className="eyebrow">LATEST TELEMETRY</p><h2>Sensor snapshot</h2></div><Link to="/monitoring">View monitoring <ArrowRight size={16} /></Link></section>
    <div className="sensor-grid">{data.measures.length ? data.measures.map((m) => <SensorCard measurement={m} key={m.id || `${m.sensor_type}-${m.measured_at}`} />) : <EmptyState title="No recent sensor measurements" />}</div>
    <section className="two-column"><div className="card list-card"><div className="card-title"><div><p className="eyebrow">RECENT ALERTS</p><h2>Alert activity</h2></div><BellRing /></div>{data.alerts.slice(0, 3).length ? data.alerts.slice(0, 3).map((a) => <div className="compact-alert" key={a.id}><span className={`level-dot ${String(a.alert_level).toLowerCase()}`} /><div><strong>{a.alert_level || 'Risk'} alert</strong><small>{a.message || 'Backend alert'} · {formatDate(a.created_at)}</small></div></div>) : <p className="muted">No alerts returned for this patient.</p>}</div>
      <div className="card information-card"><p className="eyebrow">CLINICAL SAFETY</p><h2>Decision support only</h2><p>ExacerbAlert displays model outputs from the backend. It does not diagnose COPD or replace clinical assessment.</p></div></section>
  </div>
}
