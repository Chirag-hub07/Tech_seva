import { Activity, CalendarDays, ShieldCheck } from 'lucide-react'
import EmptyState from '../components/EmptyState'

export default function PatientDetails({ selectedPatient, isDemoMode }) {
  if (!selectedPatient) {
    return <EmptyState title="No participant selected" detail="Select a participant from the selector to review details." />
  }

  const created = selectedPatient.created_at
    ? new Date(selectedPatient.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' })
    : 'Not recorded'

  const participantLabel = selectedPatient.participant_id || selectedPatient.patient_id || `ID ${selectedPatient.id}`
  const statusLabel = selectedPatient.monitoring_status || 'Not recorded in cohort dataset'
  const cohortBadge = selectedPatient.monitoring_status
    ? `${selectedPatient.monitoring_status} monitoring`
    : 'Cohort participant'

  return (
    <div className="page profile-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">PATIENT RECORD</p>
          <h2>Patient profile</h2>
          <p>Participant-level monitoring information and cohort metadata.</p>
        </div>
        <div className="profile-status">
          <span />
          <strong>{cohortBadge}</strong>
        </div>
      </div>

      <section className="profile-hero">
        <div className="profile-avatar">{String(participantLabel).slice(-3)}</div>
        <div>
          <p className="eyebrow">COPD STUDY PARTICIPANT</p>
          <h3>{participantLabel}</h3>
          <span>{selectedPatient.country ? `Cohort site: ${selectedPatient.country}` : 'Country not recorded'}</span>
        </div>
        <div className="profile-hero-note">
          <ShieldCheck />
          <span>PostgreSQL participant record (read-only)</span>
        </div>
      </section>

      <section className="details-grid card">
        {[
          ['Participant ID', participantLabel],
          ['Study Cohort Country', selectedPatient.country || 'Not recorded'],
          ['Monitoring Status', statusLabel],
          ['Enrolled / Record Created', created],
        ].map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      <section className="profile-insights">
        <article className="card">
          <Activity />
          <div>
            <p className="eyebrow">TELEMETRY ACCESS</p>
            <h3>Sensor streams</h3>
            <p>High-frequency biometric telemetry is delivered from the Supabase backend across all 8 TOLIFE streams.</p>
          </div>
        </article>
        <article className="card">
          <CalendarDays />
          <div>
            <p className="eyebrow">DATA TIMELINE</p>
            <h3>Longitudinal record</h3>
            <p>Navigate to Sensor Monitoring to review historical trends over 7d, 14d, 30d, 60d, 90d, or all recorded windows.</p>
          </div>
        </article>
      </section>

      <p className="page-note">
        {isDemoMode
          ? 'Demo mode active: using fictional records for user interface evaluation.'
          : 'Live Supabase connection: displaying authenticated participant metadata. Clinical assessments remain server-controlled.'}
      </p>
    </div>
  )
}
