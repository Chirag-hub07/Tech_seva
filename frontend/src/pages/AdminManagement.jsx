import { CheckCircle2, Key, RefreshCw, Shield, ShieldAlert, ShieldCheck, UserCheck, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { getAdminUsers, updateUserPatientAccess, updateUserRole } from '../services/api'

export default function AdminManagement() {
  const { user } = useAuth()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionSuccess, setActionSuccess] = useState('')
  const [editingPatientUser, setEditingPatientUser] = useState(null)
  const [patientInput, setPatientInput] = useState('')

  const loadUsers = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getAdminUsers()
      setUsers(data)
    } catch (err) {
      setError(err.message || 'Failed to load user roster.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
  }, [])

  const handleRoleChange = async (targetUser, newRole) => {
    setError('')
    setActionSuccess('')
    if (targetUser.id === user.id && newRole !== 'administrator') {
      setError('Self-demotion prevented: Administrators cannot remove their own administrator privileges.')
      return
    }

    try {
      await updateUserRole(targetUser.id, newRole)
      setActionSuccess(`Role for ${targetUser.email || targetUser.id} updated to ${newRole}.`)
      loadUsers()
    } catch (err) {
      setError(err.message || 'Failed to update user role.')
    }
  }

  const handleSavePatientAccess = async (targetUser) => {
    setError('')
    setActionSuccess('')
    const pids = patientInput
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0)

    try {
      await updateUserPatientAccess(targetUser.id, pids)
      setActionSuccess(`Assigned patients for ${targetUser.email || targetUser.id} updated: [${pids.join(', ')}].`)
      setEditingPatientUser(null)
      loadUsers()
    } catch (err) {
      setError(err.message || 'Failed to update patient access permissions.')
    }
  }

  return (
    <div className="page-container admin-page" style={{ padding: '2rem' }}>
      <header className="page-header" style={{ marginBottom: '1.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <p className="eyebrow" style={{ color: 'var(--color-primary, #0d9488)' }}>ADMINISTRATION & SECURITY</p>
          <h1 style={{ fontSize: '1.75rem', margin: '0.25rem 0' }}>User & Access Management</h1>
          <p style={{ color: 'var(--color-text-muted)', margin: 0 }}>
            Manage application roles and enforce patient-level authorization for clinicians.
          </p>
        </div>
        <button
          className="button"
          onClick={loadUsers}
          disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          <span>Refresh Roster</span>
        </button>
      </header>

      {/* Security Principles Banner */}
      <div className="card" style={{ marginBottom: '1.5rem', background: 'rgba(13, 148, 136, 0.05)', borderLeft: '4px solid #0d9488' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
          <ShieldCheck size={24} style={{ color: '#0d9488', flexShrink: 0, marginTop: '2px' }} />
          <div>
            <h3 style={{ margin: '0 0 0.4rem 0', fontSize: '1rem' }}>Administrator RBAC & Least-Privilege Safeguards</h3>
            <ul style={{ margin: 0, paddingLeft: '1.25rem', color: 'var(--color-text-muted)', fontSize: '0.9rem', lineHeight: '1.6' }}>
              <li><strong>Server-controlled roles:</strong> Roles are stored in Supabase <code>app_metadata</code> and verified via asymmetric ECDSA ES256 signatures. Client-editable <code>user_metadata</code> is strictly ignored.</li>
              <li><strong>Deny-by-default patient access:</strong> Clinicians can only query patients explicitly listed in their assigned cohort. Administrators cannot access clinical telemetry without explicit clinical permissions.</li>
              <li><strong>Self-demotion protection:</strong> Administrators cannot revoke their own administrator rights.</li>
            </ul>
          </div>
        </div>
      </div>

      {error && (
        <div style={{ padding: '0.85rem 1rem', background: 'rgba(225, 29, 72, 0.1)', border: '1px solid rgba(225, 29, 72, 0.2)', borderRadius: '6px', color: '#e11d48', marginBottom: '1.25rem' }}>
          {error}
        </div>
      )}

      {actionSuccess && (
        <div style={{ padding: '0.85rem 1rem', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: '6px', color: '#059669', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <CheckCircle2 size={18} />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* Users Roster */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
          <h2 style={{ fontSize: '1.15rem', margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Users size={20} />
            <span>Registered Accounts ({users.length})</span>
          </h2>
        </div>

        {loading ? (
          <p style={{ color: 'var(--color-text-muted)' }}>Loading user roster...</p>
        ) : users.length === 0 ? (
          <p style={{ color: 'var(--color-text-muted)' }}>No user accounts found.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-border)', color: 'var(--color-text-muted)' }}>
                  <th style={{ padding: '0.75rem 0.5rem' }}>User / Email</th>
                  <th style={{ padding: '0.75rem 0.5rem' }}>Role</th>
                  <th style={{ padding: '0.75rem 0.5rem' }}>Authorized Patients</th>
                  <th style={{ padding: '0.75rem 0.5rem', textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => {
                  const isCurrent = u.id === user?.id
                  const isEditingPatient = editingPatientUser?.id === u.id
                  return (
                    <tr key={u.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                      <td style={{ padding: '0.85rem 0.5rem' }}>
                        <div style={{ fontWeight: 600 }}>{u.email || 'Unregistered Email'}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', fontFamily: 'monospace' }}>
                          {u.id} {isCurrent && <span style={{ color: '#0d9488', fontWeight: 600 }}>(You)</span>}
                        </div>
                      </td>
                      <td style={{ padding: '0.85rem 0.5rem' }}>
                        <select
                          value={u.role || ''}
                          onChange={(e) => handleRoleChange(u, e.target.value)}
                          disabled={isCurrent}
                          title={isCurrent ? 'Self-demotion disabled' : 'Change role'}
                          style={{
                            padding: '0.35rem 0.65rem',
                            borderRadius: '6px',
                            border: '1px solid var(--color-border)',
                            background: u.role === 'administrator' ? 'rgba(13, 148, 136, 0.1)' : 'rgba(59, 130, 246, 0.1)',
                            color: u.role === 'administrator' ? '#0d9488' : '#2563eb',
                            fontWeight: 600,
                            fontSize: '0.85rem',
                          }}
                        >
                          <option value="clinician">Clinician</option>
                          <option value="administrator">Administrator</option>
                        </select>
                      </td>
                      <td style={{ padding: '0.85rem 0.5rem' }}>
                        {isEditingPatient ? (
                          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                            <input
                              type="text"
                              value={patientInput}
                              onChange={(e) => setPatientInput(e.target.value)}
                              placeholder="e.g. 1, 2, 3"
                              style={{
                                padding: '0.3rem 0.5rem',
                                borderRadius: '4px',
                                border: '1px solid var(--color-border)',
                                fontSize: '0.85rem',
                                width: '160px',
                              }}
                            />
                            <button
                              className="button button-primary"
                              onClick={() => handleSavePatientAccess(u)}
                              style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem' }}
                            >
                              Save
                            </button>
                            <button
                              className="button"
                              onClick={() => setEditingPatientUser(null)}
                              style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem' }}
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <span style={{ color: u.patient_ids?.length ? 'var(--color-text)' : 'var(--color-text-muted)' }}>
                              {u.patient_ids?.length
                                ? `[Patients ${u.patient_ids.join(', ')}]`
                                : '(None assigned — Deny by default)'}
                            </span>
                            <button
                              className="button"
                              onClick={() => {
                                setEditingPatientUser(u)
                                setPatientInput((u.patient_ids || []).join(', '))
                              }}
                              style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem' }}
                            >
                              Edit
                            </button>
                          </div>
                        )}
                      </td>
                      <td style={{ padding: '0.85rem 0.5rem', textAlign: 'right' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                          {u.created_at ? new Date(u.created_at).toLocaleDateString() : 'Active'}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
