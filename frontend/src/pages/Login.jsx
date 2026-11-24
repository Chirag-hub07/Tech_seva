import { useEffect, useState } from 'react'
import { Activity, Eye, EyeOff, HeartPulse, LockKeyhole, Mail, ShieldCheck, UserRound } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { isSupabaseConfigured } from '../lib/supabase'
import { isDemoMode } from '../services/api'

export default function Login() {
  const { signIn, signUp, resetPassword, updatePassword, passwordRecovery } = useAuth()
  const [mode, setMode] = useState(passwordRecovery ? 'update-password' : 'login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (passwordRecovery) setMode('update-password')
  }, [passwordRecovery])

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    setMessage('')
    setSubmitting(true)
    try {
      if (mode === 'login') {
        await signIn(email.trim(), password)
      } else if (mode === 'update-password') {
        await updatePassword(password)
        setMessage('Password updated successfully. You can continue to the workspace.')
        setMode('login')
      } else if (mode === 'signup') {
        await signUp(email.trim(), password, fullName.trim())
        setMessage('Account created. Check your email if confirmation is required.')
        setMode('login')
      } else {
        await resetPassword(email.trim())
        setMessage('If the email exists, password-reset instructions have been sent.')
      }
    } catch (requestError) {
      setError(requestError.message || 'Authentication could not be completed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-visual" aria-label="ExacerbAlert product information">
        <div className="auth-brand"><span className="brand-mark"><HeartPulse /></span><span>Exacerb<span>Alert</span></span></div>
        <div className="auth-visual-copy">
          <p className="eyebrow">COPD EARLY-WARNING SYSTEM</p>
          <h1>Secure access to patient monitoring</h1>
          <p>Review longitudinal telemetry and model-supported risk information in one protected workspace.</p>
        </div>
        <div className="auth-security-list">
          <span><ShieldCheck />Protected clinical workspace</span>
          <span><Activity />Longitudinal monitoring</span>
          <span><LockKeyhole />Session-based authentication</span>
        </div>
      </section>

      <section className="auth-panel">
        <form className="auth-card" onSubmit={submit}>
          <p className="eyebrow">{mode === 'signup' ? 'CREATE ACCOUNT' : mode === 'reset' ? 'RECOVER ACCESS' : mode === 'update-password' ? 'SET NEW PASSWORD' : 'WELCOME BACK'}</p>
          <h2>{mode === 'signup' ? 'Create your account' : mode === 'reset' ? 'Reset your password' : mode === 'update-password' ? 'Choose a new password' : 'Sign in to ExacerbAlert'}</h2>
          <p className="auth-subtitle">
            {mode === 'signup' ? 'Request access to the monitoring workspace.' : mode === 'reset' ? 'We will send recovery instructions to your email.' : mode === 'update-password' ? 'Enter a new password for your authorized account.' : 'Use your authorized account to continue.'}
          </p>

          {isDemoMode && !isSupabaseConfigured && (
            <div className="auth-config-note">Demo authentication is active because Supabase is not configured. Use any valid email and a password of at least 6 characters.</div>
          )}
          {!isDemoMode && !isSupabaseConfigured && (
            <div className="auth-config-note">Authentication is unavailable. Add VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY to the frontend environment.</div>
          )}

          {mode === 'signup' && (
            <label className="auth-field"><span>Full name</span><div><UserRound /><input value={fullName} onChange={(event) => setFullName(event.target.value)} autoComplete="name" required placeholder="Dr. Alex Morgan" /></div></label>
          )}
          {mode !== 'update-password' && (
            <label className="auth-field"><span>Email address</span><div><Mail /><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required placeholder="name@example.com" /></div></label>
          )}
          {mode !== 'reset' && (
            <label className="auth-field"><span>Password</span><div><LockKeyhole /><input type={showPassword ? 'text' : 'password'} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} required minLength={6} placeholder="Enter your password" /><button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? <EyeOff /> : <Eye />}</button></div></label>
          )}

          {error && <div className="auth-message error">{error}</div>}
          {message && <div className="auth-message success">{message}</div>}

          {mode === 'login' && <button type="button" className="auth-text-button" onClick={() => setMode('reset')}>Forgot password?</button>}
          <button className="auth-submit" type="submit" disabled={submitting || (!isSupabaseConfigured && !isDemoMode)}>
            {submitting ? 'Please wait...' : mode === 'signup' ? 'Create account' : mode === 'reset' ? 'Send reset link' : mode === 'update-password' ? 'Update password' : 'Sign in'}
          </button>

          <div className="auth-switch">
            {mode === 'signup' ? 'Already have an account?' : mode === 'reset' ? 'Remembered your password?' : 'New to ExacerbAlert?'}
            <button type="button" onClick={() => { setMode(mode === 'signup' || mode === 'reset' ? 'login' : 'signup'); setError(''); setMessage('') }}>
              {mode === 'signup' || mode === 'reset' ? 'Sign in' : 'Create account'}
            </button>
          </div>
        </form>
        <p className="auth-footer">Research prototype · Not for emergency care or diagnostic use</p>
      </section>
    </main>
  )
}
