// Fictional records for interface testing only. They are not clinical data,
// device measurements, or ML predictions.
export const demoPatients = [
  { id: 101, participant_id: 'DEMO-001', country: 'Germany', monitoring_status: 'Active', created_at: '2026-11-01T09:00:00Z' },
  { id: 102, participant_id: 'DEMO-002', country: 'Spain', monitoring_status: 'Active', created_at: '2026-11-02T09:00:00Z' },
]

const now = new Date('2026-11-21T09:30:00Z')
const at = (days, hour = 9) => new Date(now.getTime() - days * 86400000 + hour * 3600000).toISOString()
const sensorValues = {
  BRI: ['breathing_rate', [17.4, 18.1, 17.8, 18.6, 19.2, 18.4, 18.9]],
  EI: ['temperature', [22.1, 22.6, 23.0, 22.4, 23.2, 22.8, 23.4]],
  MI: ['activity_score', [63, 58, 61, 55, 52, 57, 54]],
  PEI: ['spo2', [96, 96, 95, 96, 95, 95, 94]],
  PRVI: ['heart_rate_variability', [43, 41, 42, 39, 38, 40, 37]],
  SHRI: ['sleeping_heart_rate', [67, 68, 67, 69, 70, 69, 71]],
  SII: ['sound_intensity', [34, 35, 33, 36, 37, 35, 38]],
  SQI: ['sleep_quality_score', [82, 80, 78, 76, 74, 77, 73]],
}

const measurementsFor = (patientId, type) => {
  const [field, values] = sensorValues[type]
  const offset = patientId === 102 ? -1 : 0
  return values.map((value, index) => ({ id: `${patientId}-${type}-${index}`, sensor_type: type, measured_at: at(6 - index), measurements: { [field]: value + offset }, is_valid: !(type === 'SII' && index === 2) }))
}

export const demoLatestMeasurements = (patientId) => Object.keys(sensorValues).map((type) => measurementsFor(patientId, type).at(-1))
export const demoMeasurements = (patientId, sensorType) => measurementsFor(patientId, sensorType)
export const demoLatestPrediction = (patientId) => ({ id: `prediction-${patientId}-latest`, patient_id: patientId, risk_probability: patientId === 101 ? 0.42 : 0.18, risk_level: patientId === 101 ? 'MEDIUM' : 'LOW', prediction_horizon_days: 7, prediction_timestamp: at(0), model_version: 'demo-ui-v1' })
export const demoPredictionHistory = (patientId) => [
  { ...demoLatestPrediction(patientId), id: `prediction-${patientId}-1`, prediction_timestamp: at(0) },
  { ...demoLatestPrediction(patientId), id: `prediction-${patientId}-2`, risk_probability: patientId === 101 ? 0.36 : 0.14, risk_level: 'LOW', prediction_timestamp: at(2) },
  { ...demoLatestPrediction(patientId), id: `prediction-${patientId}-3`, risk_probability: patientId === 101 ? 0.29 : 0.12, risk_level: 'LOW', prediction_timestamp: at(5) },
]

let demoAlerts = [
  { id: 'demo-alert-1', patient_id: 101, alert_level: 'MEDIUM', message: 'Demo alert: a follow-up assessment may be appropriate.', status: 'pending', created_at: at(0) },
  { id: 'demo-alert-2', patient_id: 101, alert_level: 'LOW', message: 'Demo alert: monitoring trend recorded.', status: 'acknowledged', created_at: at(3) },
]
export const getDemoAlerts = (patientId) => demoAlerts.filter((alert) => alert.patient_id === patientId).map((alert) => ({ ...alert }))
export const acknowledgeDemoAlert = (id) => {
  demoAlerts = demoAlerts.map((alert) => alert.id === id ? { ...alert, status: 'acknowledged', acknowledged_at: now.toISOString() } : alert)
  return demoAlerts.find((alert) => alert.id === id)
}
