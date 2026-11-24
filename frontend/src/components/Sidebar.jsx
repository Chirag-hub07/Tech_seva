import { Activity, BellRing, ChartNoAxesCombined, HeartPulse, LayoutDashboard, Users } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const items = [
  ['/dashboard', LayoutDashboard, 'Overview'],
  ['/patients', Users, 'Patient Profile'],
  ['/monitoring', Activity, 'Sensor Telemetry'],
  ['/predictions', ChartNoAxesCombined, 'Risk Forecasts'],
  ['/alerts', BellRing, 'Clinical Alerts'],
]

export default function Sidebar({ collapsed }) {
  return (
    <aside className={`sidebar ${collapsed ? 'is-collapsed' : ''}`}>
      {/* Brand */}
      <div className="brand">
        <span className="brand-mark">
          <HeartPulse size={20} />
        </span>
        <span className="brand-title">
          Exacerb<span>Alert</span>
        </span>
      </div>

      {/* Navigation */}
      <nav>
        <p className="nav-section-label">Clinical Workflow</p>
        {items.map(([to, Icon, label]) => (
          <NavLink to={to} key={to} title={collapsed ? label : undefined} className={({ isActive }) => (isActive ? 'active' : '')}>
            <Icon size={19} className="nav-icon" />
            <span className="nav-text">{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Sidebar Footer */}
      <div className="sidebar-footer">
        <div className="sidebar-footer-inner" title="Research Prototype · TOLIFE Study">
          <span className="status-dot" />
          <div className="sidebar-footer-text">
            <strong>COPD Study Prototype</strong>
            <small>Not for acute triage</small>
          </div>
        </div>
      </div>
    </aside>
  )
}
