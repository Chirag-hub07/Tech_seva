const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '')
export const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true'
const demo = async () => import('./demoData')

async function request(path, options = {}) {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { Accept: 'application/json', ...options.headers }, ...options,
  })
  if (!response.ok) throw new Error(`Could not reach the monitoring service (${response.status}).`)
  return response.json()
}

const asArray = (value) => Array.isArray(value) ? value : (value?.items || value?.data || [])
export const getPatients = async () => isDemoMode ? (await demo()).demoPatients : asArray(await request('/patients'))
export const getPatient = async (id) => isDemoMode ? (await demo()).demoPatients.find((patient) => patient.id === Number(id)) : request(`/patients/${id}`)
export const getLatestPrediction = async (id) => isDemoMode ? (await demo()).demoLatestPrediction(Number(id)) : request(`/patients/${id}/predictions/latest`)
export const getPredictionHistory = async (id) => isDemoMode ? (await demo()).demoPredictionHistory(Number(id)) : asArray(await request(`/patients/${id}/predictions`))
export const getMeasurements = async (id, sensor, range = '7d') => isDemoMode ? (await demo()).demoMeasurements(Number(id), sensor, range) : asArray(await request(`/patients/${id}/measurements?sensor_type=${encodeURIComponent(sensor)}&range=${range}`))
export const getLatestMeasurements = async (id) => isDemoMode ? (await demo()).demoLatestMeasurements(Number(id)) : asArray(await request(`/patients/${id}/measurements/latest`))
export const getAlerts = async (id) => isDemoMode ? (await demo()).getDemoAlerts(Number(id)) : asArray(await request(`/patients/${id}/alerts`))
export const acknowledgeAlert = async (id) => isDemoMode ? (await demo()).acknowledgeDemoAlert(id) : request(`/alerts/${id}/acknowledge`, { method: 'PATCH' })
