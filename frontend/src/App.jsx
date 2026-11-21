import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import { getPatients, isDemoMode } from './services/api'
import Dashboard from './pages/Dashboard'
import PatientDetails from './pages/PatientDetails'
import SensorMonitoring from './pages/SensorMonitoring'
import Predictions from './pages/Predictions'
import Alerts from './pages/Alerts'

export default function App() {
  const [patients, setPatients] = useState([])
  const [selectedPatient, setSelectedPatient] = useState(null)
  const [patientError, setPatientError] = useState('')

  useEffect(() => {
    getPatients().then((data) => {
      setPatients(data)
      setSelectedPatient(data[0] ?? null)
    }).catch((error) => setPatientError(error.message))
  }, [])

  const shared = { patients, selectedPatient, setSelectedPatient, patientError, isDemoMode }
  return <div className="app-shell">
    <Sidebar />
    <main className="main-content">
      <Topbar {...shared} />
      <Routes>
        <Route path="/dashboard" element={<Dashboard {...shared} />} />
        <Route path="/patients" element={<PatientDetails {...shared} />} />
        <Route path="/monitoring" element={<SensorMonitoring {...shared} />} />
        <Route path="/predictions" element={<Predictions {...shared} />} />
        <Route path="/alerts" element={<Alerts {...shared} />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </main>
  </div>
}
