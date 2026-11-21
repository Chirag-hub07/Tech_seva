const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { Accept: 'application/json', ...options.headers }, ...options,
  })
  if (!response.ok) throw new Error(`Could not reach the monitoring service (${response.status}).`)
  return response.json()
}

const asArray = (value) => Array.isArray(value) ? value : (value?.items || value?.data || [])
export const getPatients = async () => asArray(await request('/patients'))
export const getPatient = (id) => request(`/patients/${id}`)
export const getLatestPrediction = (id) => request(`/patients/${id}/predictions/latest`)
export const getPredictionHistory = async (id) => asArray(await request(`/patients/${id}/predictions`))
export const getMeasurements = async (id, sensor, range = '7d') =>
  asArray(await request(`/patients/${id}/measurements?sensor_type=${encodeURIComponent(sensor)}&range=${range}`))
export const getLatestMeasurements = async (id) => asArray(await request(`/patients/${id}/measurements/latest`))
export const getAlerts = async (id) => asArray(await request(`/patients/${id}/alerts`))
export const acknowledgeAlert = (id) => request(`/alerts/${id}/acknowledge`, { method: 'PATCH' })
