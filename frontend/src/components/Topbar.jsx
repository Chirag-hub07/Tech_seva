import { CircleHelp, Menu, ShieldCheck } from 'lucide-react'
import PatientSelector from './PatientSelector'
export default function Topbar({ patients, selectedPatient, setSelectedPatient, isDemoMode }) {
  return <header className="topbar"><button className="icon-button mobile-menu" aria-label="Open menu"><Menu /></button><div><p className="eyebrow">COPD EARLY-WARNING SYSTEM</p><h1>Patient monitoring</h1></div>
    <div className="topbar-actions">{isDemoMode && <span className="demo-badge">Demo data</span>}<PatientSelector patients={patients} selected={selectedPatient} onChange={setSelectedPatient} /><button className="icon-button" aria-label="Security information"><ShieldCheck /></button><button className="icon-button" aria-label="Help"><CircleHelp /></button></div>
  </header>
}
