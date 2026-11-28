import {
  CircleHelp,
  LockKeyhole,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  ShieldCheck,
  Sun,
  UserCheck,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
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
}) {
  const { user, role, switchRole, switchDemoRole } = useAuth()
  const [panel, setPanel] = useState(null)

  const content =
    panel === 'security'
      ? {
          title: 'Authentication & Privacy',
          icon: <LockKeyhole />,
          body: 'Protected with Supabase Auth and FastAPI ES256 asymmetric signature verification. Least privilege is enforced: Clinicians only access assigned cohorts, and Administrators manage user roles without direct clinical record access.',
        }
      : {
          title: 'Using ExacerbAlert',
          icon: <CircleHelp />,
          body: 'Choose a patient, review the dashboard, explore sensor trends, and review predictions and alerts. Switch roles to evaluate Clinician vs Administrator perspectives.',
        }

  const isClinician = role === 'clinician'
  const isAdmin = role === 'administrator'

  return (
    <>
      <header className="topbar">
        <button
          className="icon-button sidebar-toggle"
          onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          aria-label={`${isSidebarCollapsed ? 'Open' : 'Close'} sidebar`}
          title={`${isSidebarCollapsed ? 'Open' : 'Close'} sidebar`}
        >
          {isSidebarCollapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
        </button>
        <button className="icon-button mobile-menu" aria-label="Open menu">
          <Menu />
        </button>
        <div>
          <p className="eyebrow">COPD EARLY-WARNING SYSTEM</p>
          <h1>{isAdmin ? 'System Administration' : 'Patient monitoring'}</h1>
        </div>

        <div className="topbar-actions">
          {/* Active Role Indicator (Interactive switcher strictly in Demo Mode; Read-only badge in Live Mode) */}
          {user && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              {isDemoMode && <span className="demo-badge">Demo data</span>}
              {isDemoMode ? (
                <button
                  className="button"
                  onClick={() => (switchRole || switchDemoRole)(isAdmin ? 'clinician' : 'administrator')}
                  style={{
                    padding: '0.3rem 0.65rem',
                    fontSize: '0.8rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    borderRadius: '20px',
                  }}
                  title="Click to toggle active application role (Demo mode only)"
                >
                  <UserCheck size={14} />
                  <span>
                    Role: <strong>{isAdmin ? 'Administrator' : 'Clinician'}</strong>
                  </span>
                </button>
              ) : (
                <span
                  style={{
                    padding: '0.3rem 0.65rem',
                    fontSize: '0.8rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.35rem',
                    borderRadius: '20px',
                    border: '1px solid var(--color-border)',
                    background: 'var(--color-bg-secondary, rgba(0,0,0,0.03))',
                    color: 'var(--color-text)',
                  }}
                  title="Verified role derived from active Supabase session"
                >
                  <UserCheck size={14} />
                  <span>
                    Role: <strong>{isAdmin ? 'Administrator' : 'Clinician'}</strong>
                  </span>
                </span>
              )}
            </div>
          )}

          {/* Patient Selector (shown for clinicians or users with assigned patients) */}
          {isClinician ? (
            <PatientSelector
              patients={patients}
              selected={selectedPatient}
              onChange={setSelectedPatient}
            />
          ) : (
            <span
              style={{
                fontSize: '0.8rem',
                color: 'var(--color-text-muted)',
                padding: '0.4rem 0.75rem',
                border: '1px dashed var(--color-border)',
                borderRadius: '6px',
              }}
            >
              Admin View (Clinical data restricted)
            </span>
          )}

          <button
            className="icon-button theme-toggle"
            onClick={() => setIsDark(!isDark)}
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
            title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button
            className="icon-button"
            onClick={() => setPanel('security')}
            aria-label="Privacy and security"
            title="Privacy and security"
          >
            <ShieldCheck />
          </button>
          <button
            className="icon-button"
            onClick={() => setPanel('help')}
            aria-label="Help and usage"
            title="Help and usage"
          >
            <CircleHelp />
          </button>
        </div>
      </header>

      {panel && (
        <div className="modal-backdrop" role="presentation" onClick={() => setPanel(null)}>
          <section
            className="info-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="panel-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button className="modal-close" onClick={() => setPanel(null)} aria-label="Close panel">
              <X size={19} />
            </button>
            <div className="modal-icon">{content.icon}</div>
            <p className="eyebrow">EXACERBALERT</p>
            <h2 id="panel-title">{content.title}</h2>
            <p>{content.body}</p>
            <button className="modal-action" onClick={() => setPanel(null)}>
              Got it
            </button>
          </section>
        </div>
      )}
    </>
  )
}
