import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import RoleGuard from './components/RoleGuard'
import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import { AuthProvider, useAuth } from './context/AuthContext'
import AdminManagement from './pages/AdminManagement'
import Alerts from './pages/Alerts'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import PatientDetails from './pages/PatientDetails'
import Predictions from './pages/Predictions'
import SensorMonitoring from './pages/SensorMonitoring'
import { getPatients, isDemoMode } from './services/api'

function AppContent() {
  const { user, isAuthenticated, role, loading } = useAuth()
  const location = useLocation()

  const [patients, setPatients] = useState([])
  const [selectedPatient, setSelectedPatient] = useState(null)
  const [patientError, setPatientError] = useState('')
  const [isDark, setIsDark] = useState(() => localStorage.getItem('exacerbalert-theme') === 'dark')
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(
    () => localStorage.getItem('exacerbalert-sidebar') === 'collapsed'
  )

  useEffect(() => {
    localStorage.setItem('exacerbalert-theme', isDark ? 'dark' : 'light')
  }, [isDark])

  useEffect(() => {
    localStorage.setItem('exacerbalert-sidebar', isSidebarCollapsed ? 'collapsed' : 'expanded')
  }, [isSidebarCollapsed])

  // Load patients only when user is clinician or has patient assignments
  useEffect(() => {
    if (!isAuthenticated || role === 'administrator') {
      setPatients([])
      setSelectedPatient(null)
      return
    }

    let isSubscribed = true
    getPatients()
      .then((data) => {
        if (!isSubscribed) return
        setPatients(data)
        setSelectedPatient(data[0] ?? null)
        setPatientError('')
      })
      .catch((error) => {
        if (!isSubscribed) return
        setPatientError(error.message)
      })

    return () => {
      isSubscribed = false
    }
  }, [isAuthenticated, role])

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{ color: 'var(--color-text-muted)' }}>Verifying authentication session...</p>
      </div>
    )
  }

  if (!isAuthenticated && location.pathname !== '/login') {
    return <Login />
  }

  const shared = {
    patients,
    selectedPatient,
    setSelectedPatient,
    patientError,
    isDemoMode,
    isDark,
    setIsDark,
    isSidebarCollapsed,
    setIsSidebarCollapsed,
  }

  const defaultRedirect = role === 'administrator' ? '/admin' : '/dashboard'

  return (
    <div className={`app-shell ${isDark ? 'theme-dark' : ''} ${isSidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar collapsed={isSidebarCollapsed} />
      <main className="main-content">
        <Topbar {...shared} />
        <Routes>
          <Route path="/login" element={isAuthenticated ? <Navigate to={defaultRedirect} replace /> : <Login />} />

          {/* Clinical Views (Clinician only) */}
          <Route
            path="/dashboard"
            element={
              <RoleGuard allowedRoles={['clinician']}>
                <Dashboard {...shared} />
              </RoleGuard>
            }
          />
          <Route
            path="/patients"
            element={
              <RoleGuard allowedRoles={['clinician']}>
                <PatientDetails {...shared} />
              </RoleGuard>
            }
          />
          <Route
            path="/monitoring"
            element={
              <RoleGuard allowedRoles={['clinician']}>
                <SensorMonitoring {...shared} />
              </RoleGuard>
            }
          />
          <Route
            path="/predictions"
            element={
              <RoleGuard allowedRoles={['clinician']}>
                <Predictions {...shared} />
              </RoleGuard>
            }
          />
          <Route
            path="/alerts"
            element={
              <RoleGuard allowedRoles={['clinician']}>
                <Alerts {...shared} />
              </RoleGuard>
            }
          />

          {/* Administrator Views */}
          <Route
            path="/admin"
            element={
              <RoleGuard allowedRoles={['administrator']}>
                <AdminManagement />
              </RoleGuard>
            }
          />

          <Route path="*" element={<Navigate to={defaultRedirect} replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}
