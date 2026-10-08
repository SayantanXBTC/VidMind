import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || import.meta.env.VITE_SUPABASE_ANON_KEY

// Without Supabase settings the app runs in single-user local mode (no sign-in).
export const authEnabled = Boolean(url && key)

export const supabase = authEnabled
  ? createClient(url, key, { auth: { persistSession: true, autoRefreshToken: true } })
  : null

export async function getAccessToken() {
  if (!supabase) return null
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}
