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
  const [isDark, setIsDark] = useState(() => localStorage.getItem('exacerbalert-theme') === 'dark')
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => localStorage.getItem('exacerbalert-sidebar') === 'collapsed')

  useEffect(() => {
    getPatients().then((data) => {
      setPatients(data)
      setSelectedPatient(data[0] ?? null)
    }).catch((error) => setPatientError(error.message))
  }, [])

  useEffect(() => { localStorage.setItem('exacerbalert-theme', isDark ? 'dark' : 'light') }, [isDark])
  useEffect(() => { localStorage.setItem('exacerbalert-sidebar', isSidebarCollapsed ? 'collapsed' : 'expanded') }, [isSidebarCollapsed])

  const shared = { patients, selectedPatient, setSelectedPatient, patientError, isDemoMode, isDark, setIsDark, isSidebarCollapsed, setIsSidebarCollapsed }
  return <div className={`app-shell ${isDark ? 'theme-dark' : ''} ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
    <Sidebar collapsed={isSidebarCollapsed} />
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
