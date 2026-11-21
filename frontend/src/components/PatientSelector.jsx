import { Check, ChevronDown, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

export default function PatientSelector({ patients, selected, onChange }) {
  const [open, setOpen] = useState(false)
  const container = useRef(null)
  useEffect(() => {
    const closeOnOutsideClick = (event) => { if (!container.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('mousedown', closeOnOutsideClick)
    return () => document.removeEventListener('mousedown', closeOnOutsideClick)
  }, [])
  const label = selected?.participant_id || selected?.patient_id || 'No patient available'
  const options = patients.map((patient) => {
    const patientLabel = patient.participant_id || patient.patient_id || `Patient ${patient.id}`
    const active = selected?.id === patient.id
    return <button key={patient.id} className={active ? 'active' : ''} onClick={() => { onChange(patient); setOpen(false) }} role="option" aria-selected={active}><span><strong>{patientLabel}</strong><small>{patient.country || 'Country not recorded'}</small></span>{active && <Check size={16} />}</button>
  })
  return <div className="patient-picker" ref={container}><span className="picker-label">Patient</span><button className="picker-trigger" onClick={() => setOpen(!open)} aria-haspopup="listbox" aria-expanded={open}><UserRound size={15} /><strong>{label}</strong><ChevronDown size={16} className={open ? 'open' : ''} /></button>{open && <div className="picker-menu" role="listbox">{options.length ? options : <p>No patient available</p>}</div>}</div>
}
