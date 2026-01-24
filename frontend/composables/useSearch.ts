/**
 * Composable for searching documents with Ragie
 * Unified semantic search for all file types
 */

export interface ScoredChunk {
  text: string
  score: number
  document_id: string
  chunk_id: string
  metadata: Record<string, any>
}

export interface SearchResponse {
  scored_chunks: ScoredChunk[]
  total_chunks: number
}

export interface SearchRequest {
  query: string
  top_k?: number
  rerank?: boolean
  group_id?: string | null
  max_chunks_per_document?: number
  modality?: string | null
}

export function useSearch() {
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

  /**
   * Search documents across all types (text, images, videos, etc.)
   * Returns semantically relevant chunks ranked by relevance
   */
  async function search(request: SearchRequest): Promise<SearchResponse> {
    try {
      const headers = {
        'Content-Type': 'application/json',
        ...(await authHeaders()),
      }

      const body: SearchRequest = {
        query: request.query,
        top_k: request.top_k ?? 8,
        rerank: request.rerank !== false,
        max_chunks_per_document: request.max_chunks_per_document ?? 0,
      }

      if (request.group_id) {
        body.group_id = request.group_id
      }

      if (request.modality) {
        body.modality = request.modality
      }

      return await $fetch<SearchResponse>(`${API_BASE}/search/retrieve`, {
        method: 'POST',
        headers,
        body,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Search failed')
    }
  }

  return {
    search,
  }
}
