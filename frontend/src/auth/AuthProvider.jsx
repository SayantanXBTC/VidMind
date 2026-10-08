import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { authEnabled, supabase } from '../services/supabase.js'
import { getAccount } from '../services/api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(authEnabled)
  const [account, setAccount] = useState(null)

  useEffect(() => {
    if (!supabase) return undefined
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession)
    })
    return () => data.subscription.unsubscribe()
  }, [])

  const signedIn = !authEnabled || Boolean(session)

  const refreshAccount = useCallback(async () => {
    try {
      setAccount(await getAccount())
    } catch {
      // limits are informational; the app works without them
    }
  }, [])

  useEffect(() => {
    if (signedIn && !loading) refreshAccount()
    if (!signedIn) setAccount(null)
  }, [signedIn, loading, session?.user?.id, refreshAccount])

  const signOut = useCallback(async () => {
    if (supabase) await supabase.auth.signOut()
  }, [])

  return (
    <AuthContext.Provider
      value={{
        authEnabled,
        loading,
        signedIn,
        session,
        user: session?.user ?? null,
        accessToken: session?.access_token ?? null,
        account,
        refreshAccount,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
