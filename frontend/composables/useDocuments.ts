/**
 * Composable for managing documents with backend-ragie
 * Unified API for all file types (text, images, videos)
 */

export type SortField = 'created_at' | 'filename' | 'page_count'
export type SortDir = 'asc' | 'desc'

export interface DocumentItem {
  id: string
  user_id: string
  filename: string
  mime_type: string
  file_size_bytes: number | null
  status: 'pending' | 'partitioning' | 'partitioned' | 'refined' | 'chunked' | 'indexed' | 'summary_indexed' | 'keyword_indexed' | 'ready' | 'failed'
  chunk_count: number | null
  page_count: number | null
  group_id: string | null
  group_name: string | null
  created_at: string
  updated_at: string
}

export interface DocumentListResponse {
  items: DocumentItem[]
  total: number
  has_more: boolean
}

export interface DocumentStatusResponse {
  id: string
  status: string
  chunk_count: number | null
  page_count: number | null
  filename: string
}

export function useDocuments() {
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
   * Upload a document to Ragie (supports all file types)
   */
  async function uploadDocument(
    file: File,
    groupId?: string
  ): Promise<DocumentItem> {
    try {
      const headers = await authHeaders()
      const fd = new FormData()
      fd.append('file', file)
      if (groupId) fd.append('group_id', groupId)

      return await $fetch<DocumentItem>(`${API_BASE}/documents/upload`, {
        method: 'POST',
        headers,
        body: fd,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Upload failed')
    }
  }

  /**
   * List all documents for the current user
   */
  async function listDocuments(params: {
    page?: number
    page_size?: number
    group_id?: string | null
    sort?: SortField
    dir?: SortDir
    search?: string
  } = {}): Promise<DocumentListResponse> {
    try {
      const headers = await authHeaders()
      const sp = new URLSearchParams()

      if (params.page) sp.set('page', String(params.page))
      if (params.page_size) sp.set('page_size', String(params.page_size))
      if (params.group_id) sp.set('group_id', params.group_id)
      if (params.sort) sp.set('sort', params.sort)
      if (params.dir) sp.set('dir', params.dir)
      if (params.search) sp.set('search', params.search)

      const url = sp.toString() ? `${API_BASE}/documents/list?${sp.toString()}` : `${API_BASE}/documents/list`

      return await $fetch<DocumentListResponse>(url, {
        method: 'GET',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to load documents')
    }
  }

  /**
   * Get a single document's details
   */
  async function getDocument(docId: string): Promise<DocumentItem> {
    try {
      const headers = await authHeaders()
      return await $fetch<DocumentItem>(`${API_BASE}/documents/${docId}`, {
        method: 'GET',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to get document')
    }
  }

  /**
   * Check document processing status
   */
  async function getDocumentStatus(docId: string): Promise<DocumentStatusResponse> {
    try {
      const headers = await authHeaders()
      return await $fetch<DocumentStatusResponse>(`${API_BASE}/documents/${docId}/status`, {
        method: 'GET',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to get document status')
    }
  }

  /**
   * Poll document processing status until ready or failed
   */
  async function pollDocumentStatus(
    docId: string,
    onUpdate?: (status: DocumentStatusResponse) => void,
    maxAttempts: number = 120,
    intervalMs: number = 1000
  ): Promise<DocumentStatusResponse> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const status = await getDocumentStatus(docId)

      if (onUpdate) {
        onUpdate(status)
      }

      if (status.status === 'ready' || status.status === 'failed') {
        return status
      }

      await new Promise(resolve => setTimeout(resolve, intervalMs))
    }

    throw new Error('Document processing timeout')
  }

  /**
   * Update a document's group
   */
  async function updateDocumentGroup(docId: string, groupId: string | null): Promise<DocumentItem> {
    try {
      const headers = await authHeaders()
      const sp = new URLSearchParams()
      if (groupId) sp.set('group_id', groupId)

      const url = sp.toString() ? `${API_BASE}/documents/${docId}?${sp.toString()}` : `${API_BASE}/documents/${docId}`

      return await $fetch<DocumentItem>(url, {
        method: 'PATCH',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to update document')
    }
  }

  /**
   * Delete a document
   */
  async function deleteDocument(docId: string): Promise<void> {
    try {
      const headers = await authHeaders()
      await $fetch(`${API_BASE}/documents/${docId}`, {
        method: 'DELETE',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to delete document')
    }
  }

  return {
    uploadDocument,
    listDocuments,
    getDocument,
    getDocumentStatus,
    pollDocumentStatus,
    updateDocumentGroup,
    deleteDocument,
  }
}
