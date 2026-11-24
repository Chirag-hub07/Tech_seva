import { Check, ChevronDown, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

export default function PatientSelector({ patients, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const container = useRef(null)

  useEffect(() => {
    const closeOnOutsideClick = (event) => {
      if (!container.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsideClick)
    return () => document.removeEventListener('mousedown', closeOnOutsideClick)
  }, [])

  const label = selected?.participant_id || selected?.patient_id || 'Select participant'

  const options = patients.map((patient) => {
    const patientLabel = patient.participant_id || patient.patient_id || `Patient ${patient.id}`
    const active = selected?.id === patient.id
    return (
      <button
        key={patient.id}
        type="button"
        className={active ? 'active' : ''}
        onClick={() => {
          onChange(patient)
          setOpen(false)
        }}
        role="option"
        aria-selected={active}
      >
        <span className="picker-item-info">
          <strong>{patientLabel}</strong>
          <small>{patient.country ? `${patient.country} Cohort` : 'COPD Registry'}</small>
        </span>
        {active && <Check size={16} className="picker-check-icon" />}
      </button>
    )
  })

  return (
    <div className="patient-picker" ref={container}>
      <span className="picker-label">Participant:</span>
      <button
        type="button"
        className={`picker-trigger ${open ? 'is-open' : ''}`}
        onClick={() => setOpen(!open)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <UserRound size={15} className="picker-user-icon" />
        <strong>{label}</strong>
        <ChevronDown size={14} className={`picker-chevron ${open ? 'open' : ''}`} />
      </button>
      {open && (
        <div className="picker-menu" role="listbox">
          <div className="picker-menu-header">Select COPD Participant</div>
          <div className="picker-menu-list">{options.length ? options : <p className="picker-empty">No participants registered</p>}</div>
        </div>
      )}
    </div>
  )
}
