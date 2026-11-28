/**
 * API Service for ExacerbAlert frontend with Supabase Authentication and RBAC.
 *
 * Communicates with the FastAPI backend at VITE_API_BASE_URL (default: http://localhost:8000/api/v1).
 * Supports optional demo mode via VITE_DEMO_MODE=true.
 * When in live mode, Bearer tokens are attached to all requests, and connection
 * or authorization errors are explicitly surfaced.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
export const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true'
const demo = async () => import('./demoData')

let authToken = typeof window !== 'undefined' ? sessionStorage.getItem('exacerbalert-token') : null

/**
 * Configure active Supabase access token.
 */
export const setAuthToken = (token) => {
  authToken = token
  if (typeof window !== 'undefined') {
    if (token) {
      sessionStorage.setItem('exacerbalert-token', token)
    } else {
      sessionStorage.removeItem('exacerbalert-token')
    }
  }
}

export const getAuthToken = () => authToken

/**
 * Execute HTTP fetch with authorization headers, error parsing, and session expiry interception.
 */
async function request(path, options = {}) {
  let response
  const headers = {
    Accept: 'application/json',
    ...options.headers,
  }

  // Attach Authorization Bearer token when available
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`
  }

  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
    })
  } catch (networkError) {
    throw new Error(
      `Cannot connect to ExacerbAlert backend at ${BASE_URL}. Please ensure the FastAPI server is running.`
    )
  }

  // Handle unauthenticated (401) and forbidden (403)
  if (response.status === 401) {
    // Notify application of session expiration
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('auth:expired'))
    }
    const err = new Error('Authentication required or session expired. Please sign in.')
    err.status = 401
    throw err
  }

  if (response.status === 403) {
    let forbiddenMessage = 'Access denied. You do not have permission to view or modify this resource.'
    try {
      const errPayload = await response.json()
      if (errPayload?.error?.message) {
        forbiddenMessage = errPayload.error.message
      }
    } catch {
      // Non-JSON
    }
    const err = new Error(forbiddenMessage)
    err.status = 403
    throw err
  }

  if (!response.ok) {
    let message = `API request failed with status ${response.status}.`
    try {
      const errorPayload = await response.json()
      if (errorPayload?.error?.message) {
        message = errorPayload.error.message
      } else if (errorPayload?.detail) {
        message = typeof errorPayload.detail === 'string'
          ? errorPayload.detail
          : JSON.stringify(errorPayload.detail)
      }
    } catch {
      // Non-JSON error payload
    }
    const err = new Error(message)
    err.status = response.status
    throw err
  }

  return response.json()
}

const asArray = (value) => Array.isArray(value) ? value : (value?.items || value?.data || [])

// -----------------------------------------------------------------------------
// Authentication & Profile Endpoints
// -----------------------------------------------------------------------------

export const getMe = async () => {
  if (isDemoMode) {
    const role = localStorage.getItem('exacerbalert-demo-role') || 'clinician'
    return {
      id: role === 'administrator' ? 'demo-admin-001' : 'demo-clinician-001',
      email: role === 'administrator' ? 'admin@exacerbalert.org' : 'dr.smith@exacerbalert.org',
      role,
      patient_ids: role === 'administrator' ? [] : ['1', '2', '3', '4', '5'],
      permissions: role === 'administrator'
        ? ['admin:manage_users', 'admin:assign_roles', 'admin:manage_patient_access']
        : ['clinical:read_patients', 'clinical:read_measurements', 'clinical:read_predictions', 'clinical:read_alerts'],
    }
  }
  return request('/auth/me')
}

// -----------------------------------------------------------------------------
// Administrator Endpoints
// -----------------------------------------------------------------------------

export const getAdminUsers = async () => {
  if (isDemoMode) {
    return [
      {
        id: '550e8400-e29b-41d4-a716-446655440001',
        email: 'dr.smith@exacerbalert.org',
        role: 'clinician',
        patient_ids: ['1', '2', '3', '4', '5'],
        created_at: '2026-01-15T08:30:00Z',
      },
      {
        id: '550e8400-e29b-41d4-a716-446655440002',
        email: 'admin@exacerbalert.org',
        role: 'administrator',
        patient_ids: [],
        created_at: '2026-01-10T10:00:00Z',
      },
      {
        id: '550e8400-e29b-41d4-a716-446655440003',
        email: 'dr.garcia@exacerbalert.org',
        role: 'clinician',
        patient_ids: ['6', '7', '8'],
        created_at: '2026-02-01T12:00:00Z',
      },
    ]
  }
  return asArray(await request('/admin/users'))
}

export const updateUserRole = async (userId, role) => {
  if (isDemoMode) {
    return { id: userId, role }
  }
  return request(`/admin/users/${userId}/role`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })
}

export const updateUserPatientAccess = async (userId, patientIds) => {
  if (isDemoMode) {
    return { id: userId, patient_ids: patientIds }
  }
  return request(`/admin/users/${userId}/patient-access`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patient_ids: patientIds }),
  })
}

// -----------------------------------------------------------------------------
// Clinical Endpoints
// -----------------------------------------------------------------------------

export const getPatients = async (limit = 100, offset = 0) => {
  if (isDemoMode) {
    return (await demo()).demoPatients
  }
  return asArray(await request(`/patients?limit=${limit}&offset=${offset}`))
}

export const getPatient = async (id) => {
  if (isDemoMode) {
    return (await demo()).demoPatients.find((patient) => patient.id === Number(id))
  }
  return request(`/patients/${id}`)
}

export const getLatestPrediction = async (id) => {
  if (isDemoMode) {
    return (await demo()).demoLatestPrediction(Number(id))
  }
  return request(`/patients/${id}/predictions/latest`)
}

export const getPredictionHistory = async (id, limit = 50, offset = 0) => {
  if (isDemoMode) {
    return (await demo()).demoPredictionHistory(Number(id))
  }
  return asArray(await request(`/patients/${id}/predictions?limit=${limit}&offset=${offset}`))
}

export const getMeasurements = async (id, sensor, range = '7d', limit = 500) => {
  if (isDemoMode) {
    return (await demo()).demoMeasurements(Number(id), sensor, range)
  }
  return asArray(
    await request(
      `/patients/${id}/measurements?sensor_type=${encodeURIComponent(sensor)}&range=${range}&limit=${limit}`
    )
  )
}

export const getLatestMeasurements = async (id) => {
  if (isDemoMode) {
    return (await demo()).demoLatestMeasurements(Number(id))
  }
  return asArray(await request(`/patients/${id}/measurements/latest`))
}

export const getAlerts = async (id, status = null) => {
  if (isDemoMode) {
    return (await demo()).getDemoAlerts(Number(id))
  }
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return asArray(await request(`/patients/${id}/alerts${query}`))
}

export const acknowledgeAlert = async (id) => {
  if (isDemoMode) {
    return (await demo()).acknowledgeDemoAlert(id)
  }
  return request(`/alerts/${id}/acknowledge`, { method: 'PATCH' })
}
