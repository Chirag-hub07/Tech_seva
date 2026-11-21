import { Activity, BellRing, ChartNoAxesCombined, HeartPulse, LayoutDashboard, Users } from 'lucide-react'
import { NavLink } from 'react-router-dom'
const items = [
  ['/dashboard', LayoutDashboard, 'Overview'], ['/patients', Users, 'Patient profile'],
  ['/monitoring', Activity, 'Sensor monitoring'], ['/predictions', ChartNoAxesCombined, 'Predictions'], ['/alerts', BellRing, 'Alerts'],
]
export default function Sidebar({ collapsed }) {
  return <aside className="sidebar"><div className="brand"><span className="brand-mark"><HeartPulse /></span><span>Exacerb<span>Alert</span></span></div>
    <nav>{items.map(([to, Icon, label]) => <NavLink to={to} key={to} title={collapsed ? label : undefined}><Icon size={19} /><span>{label}</span></NavLink>)}</nav>
    <div className="sidebar-footer"><span className="status-dot" />Research prototype<br /><small>Not for emergency care</small></div>
  </aside>
}
