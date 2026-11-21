import { CircleHelp, Menu, Moon, ShieldCheck, Sun } from 'lucide-react'
import PatientSelector from './PatientSelector'
export default function Topbar({ patients, selectedPatient, setSelectedPatient, isDemoMode, isDark, setIsDark }) {
  return <header className="topbar"><button className="icon-button mobile-menu" aria-label="Open menu"><Menu /></button><div><p className="eyebrow">COPD EARLY-WARNING SYSTEM</p><h1>Patient monitoring</h1></div>
    <div className="topbar-actions">{isDemoMode && <span className="demo-badge">Demo data</span>}<PatientSelector patients={patients} selected={selectedPatient} onChange={setSelectedPatient} /><button className="icon-button theme-toggle" onClick={() => setIsDark(!isDark)} aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`} title={`Switch to ${isDark ? 'light' : 'dark'} mode`}>{isDark ? <Sun size={18} /> : <Moon size={18} />}</button><button className="icon-button" aria-label="Security information"><ShieldCheck /></button><button className="icon-button" aria-label="Help"><CircleHelp /></button></div>
  </header>
}
