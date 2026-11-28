import { HeartPulse, KeyRound, Lock, LogIn, Mail, ShieldCheck, UserCheck } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { isDemoMode } from '../services/api'

export default function Login() {
  const { login, authError } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [localError, setLocalError] = useState('')

  const handleSignIn = async (e) => {
    e?.preventDefault()
    setLocalError('')
    if (!email) {
      setLocalError('Please enter an email address.')
      return
    }
    setLoading(true)
    try {
      await login(email, password)
      navigate('/dashboard')
    } catch (err) {
      setLocalError(err.message || 'Invalid credentials. Please verify your email and password.')
    } finally {
      setLoading(false)
    }
  }

  const handleQuickLogin = async (role) => {
    setLocalError('')
    setLoading(true)
    try {
      if (role === 'clinician') {
        await login('dr.smith@exacerbalert.org', 'demo-clinician-secret', 'clinician')
      } else {
        await login('admin@exacerbalert.org', 'demo-admin-secret', 'administrator')
      }
      navigate('/dashboard')
    } catch (err) {
      setLocalError(err.message || 'Quick login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-screen" style={{ minHeight: '80vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}>
      <div className="card" style={{ maxWidth: '480px', width: '100%', padding: '2rem', boxShadow: '0 8px 30px rgba(0,0,0,0.12)' }}>
        <div style={{ textAlign: 'center', marginBottom: '1.75rem' }}>
          <div style={{ display: 'inline-flex', padding: '0.75rem', borderRadius: '12px', background: 'rgba(20, 184, 166, 0.1)', color: '#0d9488', marginBottom: '0.75rem' }}>
            <HeartPulse size={36} />
          </div>
          <h1 style={{ fontSize: '1.5rem', margin: '0 0 0.25rem 0' }}>ExacerbAlert</h1>
          <p className="eyebrow" style={{ color: 'var(--color-text-muted)' }}>SECURE CLINICAL AUTHENTICATION</p>
        </div>

        {(localError || authError) && (
          <div style={{ padding: '0.75rem 1rem', background: 'rgba(225, 29, 72, 0.1)', border: '1px solid rgba(225, 29, 72, 0.2)', borderRadius: '6px', color: '#e11d48', fontSize: '0.9rem', marginBottom: '1.25rem' }}>
            {localError || authError}
          </div>
        )}

        <form onSubmit={handleSignIn} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.4rem', color: 'var(--color-text)' }}>
              Email address
            </label>
            <div style={{ position: 'relative' }}>
              <span style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }}>
                <Mail size={18} />
              </span>
              <input
                type="email"
                placeholder="name@hospital.org"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{ width: '100%', padding: '0.65rem 0.75rem 0.65rem 2.5rem', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'var(--color-bg)', color: 'var(--color-text)' }}
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 500, marginBottom: '0.4rem', color: 'var(--color-text)' }}>
              Password / Access Token
            </label>
            <div style={{ position: 'relative' }}>
              <span style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }}>
                <Lock size={18} />
              </span>
              <input
                type="password"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ width: '100%', padding: '0.65rem 0.75rem 0.65rem 2.5rem', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'var(--color-bg)', color: 'var(--color-text)' }}
              />
            </div>
          </div>

          <button
            type="submit"
            className="button button-primary"
            disabled={loading}
            style={{ marginTop: '0.5rem', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.5rem', padding: '0.75rem' }}
          >
            <LogIn size={18} />
            <span>{loading ? 'Authenticating...' : 'Sign In'}</span>
          </button>
        </form>

        {isDemoMode && (
          <div style={{ marginTop: '1.75rem', paddingTop: '1.25rem', borderTop: '1px solid var(--color-border)' }}>
            <p className="eyebrow" style={{ textAlign: 'center', marginBottom: '0.75rem', color: 'var(--color-text-muted)' }}>
              QUICK ROLE DEMO
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <button
                type="button"
                className="button"
                onClick={() => handleQuickLogin('clinician')}
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
              >
                <UserCheck size={16} />
                <span>Dr. Smith (Clinician — Patients 1–5)</span>
              </button>
              <button
                type="button"
                className="button"
                onClick={() => handleQuickLogin('administrator')}
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
              >
                <ShieldCheck size={16} />
                <span>System Admin (Administrator)</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
