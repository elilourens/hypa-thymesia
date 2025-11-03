//  move the interface outside the function
export interface ChatMsg {
  id: string
  role: 'user' | 'assistant'
  parts: { type: 'text'; text: string }[]
  metadata?: any
}

export function useChat() {
  const supabase = useSupabaseClient()
  const API_BASE =
    useRuntimeConfig().public.apiBase ?? 'http://127.0.0.1:8000/api/v1'

  async function token() {
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token
  }

  async function authHeaders() {
    const t = await token()
    if (!t) throw new Error('Not logged in')
    return { Authorization: `Bearer ${t}` }
  }

  async function sendChatMessage(text: string): Promise<ChatMsg> {
    const headers = {
      'Content-Type': 'application/json',
      ...(await authHeaders())
    }

    const res = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ question: text })
    })

    if (!res.ok) throw new Error(`Chat failed: ${res.status}`)

    const data = await res.json()

    return {
      id: crypto.randomUUID(),
      role: 'assistant',
      parts: [{ type: 'text', text: String(data.answer ?? '') }],
      metadata: { sources: data.sources ?? {} }
    }
  }

  return { sendChatMessage }
}
