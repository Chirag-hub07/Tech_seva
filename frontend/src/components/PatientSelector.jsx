export default function PatientSelector({ patients, selected, onChange }) {
  return <label className="patient-select"><span>Patient</span><select value={selected?.id ?? ''} onChange={(e) => onChange(patients.find((p) => String(p.id) === e.target.value) || null)}>
    <option value="">No patient available</option>{patients.map((p) => <option value={p.id} key={p.id}>{p.participant_id || p.patient_id || `Patient ${p.id}`}</option>)}
  </select></label>
}
