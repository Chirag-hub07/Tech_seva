import { AlertTriangle, ArrowLeft, ShieldAlert, UserCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { isDemoMode } from '../services/api'

export default function RoleGuard({ allowedRoles, children }) {
  const { user, role, switchRole, switchDemoRole } = useAuth()

  const isAllowed = role && allowedRoles.includes(role)

  if (isAllowed) {
    return children
  }

  const requiredRoleName = allowedRoles.map((r) => r.charAt(0).toUpperCase() + r.slice(1)).join(' or ')
  const currentRoleName = role ? role.charAt(0).toUpperCase() + role.slice(1) : 'Unassigned'

  return (
    <div className="role-guard-container" style={{ padding: '2.5rem', maxWidth: '800px', margin: '2rem auto' }}>
      <div className="card" style={{ borderLeft: '4px solid var(--color-danger, #e11d48)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.25rem' }}>
          <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(225, 29, 72, 0.1)', color: 'var(--color-danger, #e11d48)' }}>
            <ShieldAlert size={28} />
          </div>
          <div>
            <p className="eyebrow" style={{ color: 'var(--color-danger, #e11d48)', margin: 0 }}>403 FORBIDDEN — LEAST PRIVILEGE ENFORCED</p>
            <h2 style={{ margin: '0.25rem 0 0 0', fontSize: '1.35rem' }}>Access Restricted for {currentRoleName} Role</h2>
          </div>
        </div>

        <p style={{ color: 'var(--color-text-muted)', lineHeight: '1.6', marginBottom: '1.5rem' }}>
          This view requires <strong>{requiredRoleName}</strong> privileges.
          Under ExacerbAlert's Role-Based Access Control (RBAC) policy:
        </p>

        <ul style={{ color: 'var(--color-text-muted)', lineHeight: '1.6', paddingLeft: '1.25rem', marginBottom: '1.5rem' }}>
          {allowedRoles.includes('clinician') && (
            <li>
              <strong>Clinical Views:</strong> Telemetry streams, risk predictions, and alerts are restricted to clinicians with explicit patient assignments.
            </li>
          )}
          {allowedRoles.includes('administrator') && (
            <li>
              <strong>Administrator Views:</strong> User account administration, role assignment, and access configuration require verified administrative privileges.
            </li>
          )}
        </ul>

        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <Link to="/dashboard" className="button" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', textDecoration: 'none' }}>
            <ArrowLeft size={16} />
            <span>Return to Overview</span>
          </Link>

          {isDemoMode ? (
            <button
              className="button button-primary"
              onClick={() => (switchRole || switchDemoRole)(allowedRoles[0])}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
            >
              <UserCheck size={16} />
              <span>Switch to {requiredRoleName} Role</span>
            </button>
          ) : (
            <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
              Role switching is disabled in live mode. Contact a system administrator to request access.
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
