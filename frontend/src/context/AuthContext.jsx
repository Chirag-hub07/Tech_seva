import { createContext, useContext, useEffect, useState } from 'react'
import { getMe, isDemoMode, setAuthToken } from '../services/api'

const AuthContext = createContext(null)

const DEMO_CLINICIAN = {
  id: '550e8400-e29b-41d4-a716-446655440001',
  email: 'dr.smith@exacerbalert.org',
  role: 'clinician',
  patient_ids: ['1', '2', '3', '4', '5'],
  permissions: [
    'clinical:read_patients',
    'clinical:read_measurements',
    'clinical:read_predictions',
    'clinical:read_alerts',
    'clinical:acknowledge_alerts',
  ],
}

const DEMO_ADMIN = {
  id: '550e8400-e29b-41d4-a716-446655440002',
  email: 'admin@exacerbalert.org',
  role: 'administrator',
  patient_ids: [],
  permissions: [
    'admin:manage_users',
    'admin:assign_roles',
    'admin:manage_patient_access',
    'admin:manage_settings',
  ],
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    if (isDemoMode) {
      const savedRole = localStorage.getItem('exacerbalert-demo-role')
      return savedRole === 'administrator' ? DEMO_ADMIN : DEMO_CLINICIAN
    }
    // In live mode, NEVER treat locally cached state as authorization proof.
    // The user identity and role are strictly derived from the backend /auth/me verification.
    return null
  })

  const [token, setTokenState] = useState(() => sessionStorage.getItem('exacerbalert-token') || null)
  const [loading, setLoading] = useState(!isDemoMode && !!sessionStorage.getItem('exacerbalert-token'))
  const [authError, setAuthError] = useState(null)

  useEffect(() => {
    const handleExpired = () => {
      logout()
      setAuthError('Your session has expired. Please sign in again.')
    }
    window.addEventListener('auth:expired', handleExpired)
    return () => window.removeEventListener('auth:expired', handleExpired)
  }, [])

  useEffect(() => {
    if (isDemoMode) {
      setLoading(false)
      return
    }

    const savedToken = sessionStorage.getItem('exacerbalert-token')
    if (savedToken) {
      setAuthToken(savedToken)
      getMe()
        .then((profile) => {
          setUser(profile)
          sessionStorage.setItem('exacerbalert-user', JSON.stringify(profile))
        })
        .catch(() => {
          logout()
        })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (email, password, requestedRole = 'clinician') => {
    setAuthError(null)
    if (isDemoMode) {
      const demoUser = requestedRole === 'administrator' || email?.includes('admin')
        ? DEMO_ADMIN
        : DEMO_CLINICIAN
      setUser(demoUser)
      localStorage.setItem('exacerbalert-demo-role', demoUser.role)
      return demoUser
    }

    try {
      const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
      const response = await fetch(`${baseUrl}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email || (requestedRole === 'administrator' ? 'admin@exacerbalert.org' : 'dr.smith@exacerbalert.org'),
          password,
          role: requestedRole || (email?.includes('admin') ? 'administrator' : 'clinician'),
        }),
      })

      if (!response.ok) {
        throw new Error('Invalid authentication credentials or token generation failed.')
      }

      const data = await response.json()
      setUser(data.user)
      setTokenState(data.access_token)
      setAuthToken(data.access_token)
      sessionStorage.setItem('exacerbalert-user', JSON.stringify(data.user))
      sessionStorage.setItem('exacerbalert-token', data.access_token)
      return data.user
    } catch (err) {
      setAuthError(err.message || 'Authentication failed')
      throw err
    }
  }

  const logout = () => {
    setUser(null)
    setTokenState(null)
    setAuthToken(null)
    sessionStorage.removeItem('exacerbalert-user')
    sessionStorage.removeItem('exacerbalert-token')
  }

  const switchRole = async (newRole) => {
    if (isDemoMode) {
      const nextUser = newRole === 'administrator' ? DEMO_ADMIN : DEMO_CLINICIAN
      setUser(nextUser)
      localStorage.setItem('exacerbalert-demo-role', nextUser.role)
      return nextUser
    }
    throw new Error('Role switching is disabled in live mode. Please log in with authorized credentials.')
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        role: user?.role || null,
        permissions: user?.permissions || [],
        patient_ids: user?.patient_ids || [],
        loading,
        authError,
        login,
        logout,
        switchRole,
        switchDemoRole: switchRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
