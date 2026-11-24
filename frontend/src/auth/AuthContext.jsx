import { createContext, useContext, useEffect, useState } from 'react'
import { isDemoMode } from '../services/api'
import { supabase } from '../lib/supabase'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [passwordRecovery, setPasswordRecovery] = useState(false)

  useEffect(() => {
    if (isDemoMode && !supabase) {
      const demoUser = sessionStorage.getItem('exacerbalert-demo-user')
      setUser(demoUser ? JSON.parse(demoUser) : null)
      setLoading(false)
      return
    }

    if (!supabase) {
      setLoading(false)
      return
    }

    supabase.auth.getSession().then(({ data }) => {
      setUser(data.session?.user ?? null)
      setLoading(false)
    })

    const { data: subscription } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY') setPasswordRecovery(true)
      if (event === 'SIGNED_OUT') setPasswordRecovery(false)
      setUser(session?.user ?? null)
      setLoading(false)
    })

    return () => subscription.subscription.unsubscribe()
  }, [])

  const signIn = async (email, password) => {
    if (isDemoMode && !supabase) {
      if (!email || password.length < 6) throw new Error('Enter a valid email and a password with at least 6 characters.')
      const demoUser = { id: 'demo-clinician', email, user_metadata: { full_name: 'Demo clinician' } }
      sessionStorage.setItem('exacerbalert-demo-user', JSON.stringify(demoUser))
      setUser(demoUser)
      return
    }

    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
  }

  const signUp = async (email, password, fullName) => {
    if (isDemoMode && !supabase) {
      await signIn(email, password)
      return
    }

    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: fullName } },
    })
    if (error) throw error
  }

  const resetPassword = async (email) => {
    if (isDemoMode && !supabase) {
      if (!email) throw new Error('Enter your email address.')
      return
    }

    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
    if (error) throw error
  }

  const updatePassword = async (password) => {
    if (isDemoMode && !supabase) {
      setPasswordRecovery(false)
      return
    }

    const { error } = await supabase.auth.updateUser({ password })
    if (error) throw error
    setPasswordRecovery(false)
  }

  const signOut = async () => {
    if (isDemoMode && !supabase) {
      sessionStorage.removeItem('exacerbalert-demo-user')
      setUser(null)
      return
    }

    const { error } = await supabase.auth.signOut()
    if (error) throw error
  }

  return (
    <AuthContext.Provider value={{ user, loading, passwordRecovery, signIn, signUp, resetPassword, updatePassword, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
