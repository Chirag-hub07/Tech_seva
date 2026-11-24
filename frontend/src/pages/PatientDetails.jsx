import {
  Activity,
  CalendarDays,
  CheckCircle2,
  FileText,
  HeartPulse,
  Radio,
  ShieldCheck,
  Stethoscope,
  UserCheck,
  Users,
  Wind,
} from 'lucide-react'
import EmptyState from '../components/EmptyState'

export default function PatientDetails({ selectedPatient, isDemoMode }) {
  if (!selectedPatient) return <EmptyState title="No participant selected" detail="Select a participant from the top navigation to view clinical records." />

  const patientId = selectedPatient.participant_id || selectedPatient.patient_id || `DEMO-00${selectedPatient.id}`
  const country = selectedPatient.country || 'Germany (TOLIFE Cohort)'
  const monitoringStatus = selectedPatient.monitoring_status || 'Active'
  const createdDate = selectedPatient.created_at
    ? new Date(selectedPatient.created_at).toLocaleDateString(undefined, { dateStyle: 'long' })
    : 'November 1, 2026'

  return (
    <div className="page patient-details-page">
      {/* Unified Professional Page Header */}
      <div className="page-header-bar">
        <div className="page-header-content">
          <div className="page-header-pre">
            <span>CLINICAL REGISTRY</span>
            <span className="page-header-sep">/</span>
            <span className="page-header-patient">{patientId}</span>
          </div>
          <div className="page-header-title-row">
            <h2>Participant Clinical Profile</h2>
            <span className="page-header-badge">TOLIFE Study</span>
          </div>
          <p className="page-header-desc">
            Participant enrollment baseline, clinical diagnosis, and continuous multi-sensor surveillance assignment.
          </p>
        </div>

        <div className="page-header-actions">
          <div className="monitoring-status-beacon">
            <span className="beacon-dot" />
            <div className="beacon-text">
              <small>STUDY STATUS</small>
              <strong>{monitoringStatus} Surveillance</strong>
            </div>
          </div>
        </div>
      </div>

      {/* Hero Patient Profile Card */}
      <section className="profile-hero">
        <div className="profile-hero-left">
          <div className="profile-avatar">
            <span>{patientId.slice(-3)}</span>
          </div>
          <div className="profile-hero-meta">
            <div className="profile-hero-badge">
              <Stethoscope size={13} />
              <span>PRIMARY DIAGNOSIS: COPD GOLD STAGE III</span>
            </div>
            <h3>{patientId}</h3>
            <p className="profile-cohort-line">
              <Users size={13} /> Regional Cohort: <strong>{country}</strong> · Enrolled: <strong>{createdDate}</strong>
            </p>
          </div>
        </div>

        <div className="profile-hero-right">
          <div className="profile-security-badge">
            <ShieldCheck size={16} />
            <div>
              <strong>De-identified Clinical Record</strong>
              <small>Data access compliant with study ethics protocol</small>
            </div>
          </div>
        </div>
      </section>

      {/* Key Clinical Demographics & Baseline Parameters */}
      <section className="profile-section-title">
        <span className="eyebrow">ENROLLMENT BASELINE</span>
        <h3>Baseline Physiological Norms & Assignment</h3>
      </section>

      <div className="details-grid">
        <div>
          <span>Participant Code</span>
          <strong>{patientId}</strong>
        </div>
        <div>
          <span>Study Center / Region</span>
          <strong>{country}</strong>
        </div>
        <div>
          <span>Baseline SpO₂ Oxygen</span>
          <strong>94.0% (Target &ge; 92%)</strong>
        </div>
        <div>
          <span>Resting Respiration</span>
          <strong>17.4 breaths / min</strong>
        </div>
        <div>
          <span>Resting Pulse (SHRI)</span>
          <strong>67 bpm (Nocturnal)</strong>
        </div>
        <div>
          <span>GOLD COPD Class</span>
          <strong>Stage III (Severe Airflow)</strong>
        </div>
        <div>
          <span>Wearable Telemetry</span>
          <strong>8 Sensor Streams Active</strong>
        </div>
        <div>
          <span>Exacerbation Risk Tier</span>
          <strong>Moderate Risk (42%)</strong>
        </div>
      </div>

      {/* Two surveillance insight cards */}
      <div className="profile-insights">
        <article className="card">
          <div className="insight-icon-box">
            <Activity size={20} />
          </div>
          <div>
            <span className="eyebrow">CONTINUOUS MONITORING</span>
            <h3>Multi-Modal Sensor Integration</h3>
            <p>
              Participant telemetry streams high-resolution indices including Breathing Rate (BRI), Peripheral Oxygen Saturation (PEI), Heart Rate Variability (PRVI), and Acoustic Cough Monitoring (SII).
            </p>
          </div>
        </article>

        <article className="card">
          <div className="insight-icon-box">
            <CalendarDays size={20} />
          </div>
          <div>
            <span className="eyebrow">EARLY WARNING HORIZON</span>
            <h3>7-Day Predictive Intervention Window</h3>
            <p>
              The AI exacerbation model computes trailing 7-day deterioration trajectories to notify healthcare providers before acute respiratory flare-ups require emergency hospitalization.
            </p>
          </div>
        </article>
      </div>

      <p className="page-note">
        {isDemoMode
          ? 'Demo Mode Active: Utilizing synthetic cohort data from the TOLIFE study for interface evaluation.'
          : 'Clinical assessments remain provider-controlled. ExacerbAlert decision support outputs are governed by server-side medical credentials.'}
      </p>
    </div>
  )
}
