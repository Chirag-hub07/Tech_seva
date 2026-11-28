import {
  Activity,
  BellRing,
  ChartNoAxesCombined,
  HeartPulse,
  LayoutDashboard,
  LogOut,
  Shield,
  UserCheck,
  Users,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const clinicalItems = [
  ['/dashboard', LayoutDashboard, 'Overview'],
  ['/patients', Users, 'Patient profile'],
  ['/monitoring', Activity, 'Sensor monitoring'],
  ['/predictions', ChartNoAxesCombined, 'Predictions'],
  ['/alerts', BellRing, 'Alerts'],
]

const adminItems = [
  ['/admin', Shield, 'User Management'],
]

export default function Sidebar({ collapsed }) {
  const { user, role, logout } = useAuth()

  const isClinician = role === 'clinician'
  const isAdmin = role === 'administrator'

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">
          <HeartPulse />
        </span>
        <span>
          Exacerb<span>Alert</span>
        </span>
      </div>

      <nav>
        {/* Clinical Section */}
        {clinicalItems.map(([to, Icon, label]) => (
          <NavLink to={to} key={to} title={collapsed ? label : undefined}>
            <Icon size={19} />
            <span>{label}</span>
          </NavLink>
        ))}

        {/* Administrator Section */}
        {isAdmin && (
          <>
            <div className="sidebar-section-divider" style={{ margin: '1rem 0 0.5rem 0', padding: '0 1rem', fontSize: '0.75rem', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {!collapsed && 'Administration'}
            </div>
            {adminItems.map(([to, Icon, label]) => (
              <NavLink to={to} key={to} title={collapsed ? label : undefined}>
                <Icon size={19} />
                <span>{label}</span>
              </NavLink>
            ))}
          </>
        )}
      </nav>

      {/* User Session Pill in Sidebar Footer */}
      <div className="sidebar-footer" style={{ borderTop: '1px solid var(--color-border)', paddingTop: '1rem', marginTop: 'auto' }}>
        {user ? (
          <div style={{ marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
              <span
                style={{
                  fontSize: '0.7rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  padding: '0.15rem 0.5rem',
                  borderRadius: '4px',
                  background: isAdmin ? 'rgba(13, 148, 136, 0.2)' : 'rgba(59, 130, 246, 0.2)',
                  color: isAdmin ? '#0d9488' : '#2563eb',
                }}
              >
                {role || 'User'}
              </span>
              <button
                onClick={logout}
                title="Sign Out"
                className="icon-button"
                style={{ padding: '4px', height: 'auto', width: 'auto' }}
              >
                <LogOut size={14} />
              </button>
            </div>
            {!collapsed && (
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user.email || 'Authenticated'}
              </div>
            )}
          </div>
        ) : null}
        <div>
          <span className="status-dot" />Research prototype<br />
          <small>Not for emergency care</small>
        </div>
      </div>
    </aside>
  )
}
