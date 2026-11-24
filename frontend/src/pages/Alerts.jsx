import { useEffect, useState } from 'react'
import AlertCard from '../components/AlertCard'
import EmptyState from '../components/EmptyState'
import { getAlerts, isDemoMode, acknowledgeAlert } from '../services/api'

export default function Alerts({ selectedPatient }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadAlerts = () => {
    if (!selectedPatient?.id) return
    let isSubscribed = true
    setLoading(true)
    setError('')

    getAlerts(selectedPatient.id)
      .then((records) => {
        if (isSubscribed) {
          setItems(records)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (isSubscribed) {
          setItems([])
          setError(err.message)
          setLoading(false)
        }
      })

    return () => {
      isSubscribed = false
    }
  }

  useEffect(() => {
    return loadAlerts()
  }, [selectedPatient?.id])

  const handleAcknowledge = async (id) => {
    if (!isDemoMode) {
      // In live mode, alert mutation is reserved for Phase 2B/3 verified write workflows
      return
    }
    try {
      await acknowledgeAlert(id)
      loadAlerts()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!selectedPatient) {
    return (
      <EmptyState
        title="No participant selected"
        detail="Select a participant from the selector to view active alerts."
      />
    )
  }

  const participantLabel = selectedPatient.participant_id || selectedPatient.patient_id || `ID ${selectedPatient.id}`

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">CLINICAL RISK NOTIFICATIONS</p>
          <h2>Alerts</h2>
          <p>Automated threshold and prediction-driven risk notifications for {participantLabel}.</p>
        </div>
        <div className="monitoring-live">
          <span />
          <span>{loading ? 'Refreshing alerts...' : 'Alert stream connected'}</span>
        </div>
      </div>

      {error ? <div className="notice" role="alert">{error}</div> : null}

      <div className="alerts-list">
        {items.length ? (
          items.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onAcknowledge={isDemoMode ? handleAcknowledge : undefined}
            />
          ))
        ) : (
          <EmptyState
            title="No alerts recorded"
            detail="There are no active or historical alerts for this participant. Important: The absence of alerts does not constitute confirmation of clinical stability."
          />
        )}
      </div>

      <p className="page-note">
        Alerts are generated automatically by backend decision-support rules. A zero-alert state indicates that no rule thresholds have fired, but clinical assessment must continue according to care protocols.
      </p>
    </div>
  )
}
