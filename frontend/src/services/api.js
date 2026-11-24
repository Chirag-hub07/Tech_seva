/**
 * API Service for ExacerbAlert frontend.
 *
 * Communicates with the FastAPI backend at VITE_API_BASE_URL (default: http://localhost:8000/api/v1).
 * Supports optional demo mode via VITE_DEMO_MODE=true.
 * When in live mode, connection errors are explicitly surfaced and never
 * silently replaced with fictional records.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
export const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true'
const demo = async () => import('./demoData')

/**
 * Execute HTTP fetch with error parsing and network diagnostics.
 */
async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { Accept: 'application/json', ...options.headers },
      ...options,
    })
  } catch (networkError) {
    throw new Error(
      `Cannot connect to ExacerbAlert backend at ${BASE_URL}. Please ensure the FastAPI server is running.`
    )
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
