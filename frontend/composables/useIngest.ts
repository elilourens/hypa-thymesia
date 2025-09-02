// composables/useIngest.ts
export function useIngest() {
  const supabase = useSupabaseClient()
  const API_BASE = useRuntimeConfig().public.apiBase ?? 'http://127.0.0.1:8000/api/v1'

  async function token() {
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token
  }

  async function authHeaders() {
    const t = await token()
    if (!t) throw new Error('Not logged in')
    return { Authorization: `Bearer ${t}` }
  }

  // --- Upload ---
  async function uploadFile(file: File) {
    try {
      const headers = await authHeaders()
      const fd = new FormData()
      fd.append('file', file)

      await $fetch(`${API_BASE}/ingest/upload-text-and-images`, {
        method: 'POST',
        headers,
        body: fd,
      })
    } catch (err: any) {
      throw new Error(err?.data || err?.message || 'Upload failed')
    }
  }

  // --- Query text ---
  async function queryText(opts: { query: string; route: 'text' | 'image'; top_k?: number }) {
    try {
      const headers = { 'Content-Type': 'application/json', ...(await authHeaders()) }

      return await $fetch<{ matches: any[] }>(`${API_BASE}/ingest/query`, {
        method: 'POST',
        headers,
        body: {
          query_text: opts.query,
          route: opts.route,
          top_k: opts.top_k ?? 10,
        },
      })
    } catch (err: any) {
      throw new Error(err?.data || err?.message || 'Text query failed')
    }
  }

  // --- Query image ---
  async function queryImage(file: File, top_k = 10) {
    try {
      const headers = { 'Content-Type': 'application/json', ...(await authHeaders()) }

      const buf = await file.arrayBuffer()
      const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)))

      return await $fetch<{ matches: any[] }>(`${API_BASE}/ingest/query`, {
        method: 'POST',
        headers,
        body: { image_b64: b64, top_k },
      })
    } catch (err: any) {
      throw new Error(err?.data || err?.message || 'Image query failed')
    }
  }

  // --- Delete document ---
  async function deleteDoc(doc_id: string) {
    try {
      const headers = await authHeaders()
      const url = `${API_BASE}/ingest/delete-document?doc_id=${encodeURIComponent(doc_id)}`

      await $fetch(url, {
        method: 'DELETE',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data || err?.message || 'Delete failed')
    }
  }

  return {
    uploadFile,
    queryText,
    queryImage,
    deleteDoc,
  }
}
