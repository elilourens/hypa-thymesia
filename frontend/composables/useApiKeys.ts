export interface ApiKey {
  id: string
  name: string
  key_prefix: string
  created_at: string
  last_used_at: string | null
  is_active: boolean
  use_count: number
}

export interface ApiKeyCreated extends ApiKey {
  key: string
}

export function useApiKeys() {
  const supabase = useSupabaseClient()
  const API_BASE = useRuntimeConfig().public.apiBase ?? 'http://127.0.0.1:8000/api/v1'

  async function authHeaders() {
    const { data } = await supabase.auth.getSession()
    const t = data.session?.access_token
    if (!t) throw new Error('Not logged in')
    return { Authorization: `Bearer ${t}` }
  }

  async function listApiKeys(): Promise<ApiKey[]> {
    const headers = await authHeaders()
    return $fetch<ApiKey[]>(`${API_BASE}/api-keys`, { headers })
  }

  async function createApiKey(name: string): Promise<ApiKeyCreated> {
    const headers = await authHeaders()
    return $fetch<ApiKeyCreated>(`${API_BASE}/api-keys`, {
      method: 'POST',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: { name },
    })
  }

  async function revokeApiKey(id: string): Promise<void> {
    const headers = await authHeaders()
    await $fetch(`${API_BASE}/api-keys/${id}`, { method: 'DELETE', headers, responseType: 'text' })
  }

  return { listApiKeys, createApiKey, revokeApiKey }
}
