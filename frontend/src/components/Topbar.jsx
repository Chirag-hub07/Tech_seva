import { CircleHelp, LockKeyhole, LogOut, Moon, PanelLeftClose, PanelLeftOpen, ShieldCheck, Sun, X } from 'lucide-react'
import { useState } from 'react'
import PatientSelector from './PatientSelector'

export default function Topbar({
  patients,
  selectedPatient,
  setSelectedPatient,
  isDemoMode,
  isDark,
  setIsDark,
  isSidebarCollapsed,
  setIsSidebarCollapsed,
  user,
  signOut,
}) {
  const [panel, setPanel] = useState(null)

  const content =
    panel === 'security'
      ? {
          title: 'Privacy & Security Protocol',
          icon: <LockKeyhole />,
          body: 'This frontend connects exclusively to authorized endpoints. De-identified longitudinal telemetry and TOLIFE clinical datasets remain secure with server-controlled access privileges.',
        }
      : {
          title: 'About ExacerbAlert Clinical System',
          icon: <CircleHelp />,
          body: 'ExacerbAlert is a context-aware clinical decision support system for COPD early exacerbation detection. It analyzes longitudinal multi-sensor telemetry (breathing rate, SpO2, sleeping heart rate, sleep quality) to generate predictive risk assessments.',
        }

  return (
    <>
      <header className="topbar">
        <div className="topbar-left">
          <button
            className="icon-button sidebar-toggle"
            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
            aria-label={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isSidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <div className="topbar-title-block">
            <span className="eyebrow">COPD CONTEXT-AWARE SYSTEM</span>
            <h1>Patient Monitoring & Early Warning</h1>
          </div>
        </div>

        <div className="topbar-actions">
          {isDemoMode && <span className="demo-badge">TOLIFE Demo Data</span>}
          <PatientSelector patients={patients} selected={selectedPatient} onChange={setSelectedPatient} />
          <div className="topbar-divider" />
          <button
            className="icon-button theme-toggle"
            onClick={() => setIsDark(!isDark)}
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
            title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
          >
            {isDark ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <button
            className="icon-button"
            onClick={() => setPanel('security')}
            aria-label="Privacy and security"
            title="Privacy and security"
          >
            <ShieldCheck size={17} />
          </button>
          <button
            className="icon-button"
            onClick={() => setPanel('help')}
            aria-label="Clinical decision support info"
            title="System documentation"
          >
            <CircleHelp size={17} />
          </button>
          <button
            className="icon-button logout-button"
            onClick={signOut}
            aria-label={`Sign out ${user?.email || ''}`}
            title="Sign out"
          >
            <LogOut size={17} />
          </button>
        </div>
      </header>

      {panel && (
        <div className="modal-backdrop" role="presentation" onClick={() => setPanel(null)}>
          <section className="info-modal" role="dialog" aria-modal="true" aria-labelledby="panel-title" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setPanel(null)} aria-label="Close panel">
              <X size={18} />
            </button>
            <div className="modal-icon">{content.icon}</div>
            <p className="eyebrow">EXACERBALERT RESEARCH PROTOCOL</p>
            <h2 id="panel-title">{content.title}</h2>
            <p>{content.body}</p>
            <button className="modal-action" onClick={() => setPanel(null)}>
              Dismiss
            </button>
          </section>
        </div>
      )}
    </>
  )
}
