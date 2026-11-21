import { useEffect, useState } from 'react'
import AlertCard from '../components/AlertCard'
import EmptyState from '../components/EmptyState'
import { acknowledgeAlert, getAlerts } from '../services/api'
export default function Alerts({ selectedPatient }) {
  const [items, setItems] = useState([])
  const [error, setError] = useState('')
  const load = () => {
    if (!selectedPatient?.id) return
    getAlerts(selectedPatient.id).then(setItems).catch((requestError) => setError(requestError.message))
  }
  useEffect(() => { load() }, [selectedPatient?.id])
  const ack = async (id) => { try { await acknowledgeAlert(id); load() } catch (requestError) { setError(requestError.message) } }
  if (!selectedPatient) return <EmptyState />
  return <div className="page"><p className="eyebrow">RISK NOTIFICATIONS</p><h2>Alerts</h2>{error ? <div className="notice">{error}</div> : null}<div className="alerts-list">{items.length ? items.map((alert) => <AlertCard key={alert.id} alert={alert} onAcknowledge={ack} />) : <EmptyState title="No alerts" detail="There are no backend alerts for the selected patient." />}</div></div>
}
