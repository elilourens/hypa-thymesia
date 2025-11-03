import { useSupabaseClient } from '#imports'

export type SortField = 'created_at' | 'size' | 'name'
export type SortDir = 'asc' | 'desc'
export type GroupSort = 'none' | 'group_then_time'

export type Modality = 'text' | 'image' | 'audio' | 'video'

export interface FileItem {
  doc_id: string
  user_id: string
  filename: string
  bucket: string
  storage_path: string
  storage_provider?: string | null
  mime_type: string
  modality: Modality | null
  size_bytes?: number | null
  chunk_count: number
  created_at: string
  group_id?: string | null
  group_name?: string | null
  group_sort_index?: number | null
}

export interface FilesResponse {
  items: FileItem[]
  page: number
  page_size: number
  total: number
  has_next: boolean
}

export function useFilesApi() {
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

  /**
   * Fetch paginated files with filters
   */
  async function listFiles(params: {
    q?: string | null
    modality?: Modality | null
    created_from?: string | null
    created_to?: string | null
    min_size?: number | null
    max_size?: number | null
    sort?: SortField
    dir?: SortDir
    page?: number
    page_size?: number
    recent?: boolean | null
    group_id?: string | null        // can be '' for "no group"
    group_sort?: GroupSort
  }): Promise<FilesResponse> {
    const headers = await authHeaders()
    const sp = new URLSearchParams()

    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) {
        if (k === 'group_id') {
          // ⚡ allow empty string so backend can interpret as "no group"
          sp.set(k, v as string)
        } else if (v !== '') {
          sp.set(k, String(v))
        }
      }
    })

    if (!sp.has('sort')) sp.set('sort', 'created_at')
    if (!sp.has('dir')) sp.set('dir', 'desc')
    if (!sp.has('page')) sp.set('page', '1')
    if (!sp.has('page_size')) sp.set('page_size', '20')
    if (!sp.has('group_sort')) sp.set('group_sort', 'none')

    try {
      return await $fetch<FilesResponse>(
        `${API_BASE}/files?${sp.toString()}`,
        { method: 'GET', headers }
      )
    } catch (err: any) {
      throw new Error(err?.data || err?.message || 'Failed to load files')
    }
  }

  /**
   * Extract Google Drive file ID from path.
   * Path format: google-drive/{FILE_ID}/{FILENAME}
   */
  function extractGoogleDriveFileId(path: string): string | null {
    const parts = path.replace('google-drive/', '').split('/')
    return parts[0] || null
  }

  /**
   * Get a signed URL for one file.
   * Handles both Supabase and Google Drive files.
   */
  async function getSignedUrl(bucket: string, path: string): Promise<string> {
    const headers = await authHeaders()
    
    try {
      // Call the backend endpoint - it will handle both Supabase and Google Drive
      const res = await $fetch<{ signed_url: string; provider?: string }>(
        `${API_BASE}/storage/signed-url`,
        { 
          method: 'GET', 
          headers, 
          params: { bucket, path } 
        }
      )
      
      if (!res.signed_url) {
        throw new Error('No signed URL returned')
      }
      
      return res.signed_url
    } catch (err: any) {
      console.error('Error getting signed URL:', err)
      throw new Error(err?.data?.detail || err?.message || 'Failed to get signed URL')
    }
  }

  /**
   * Get a thumbnail URL for Google Drive files.
   * Returns either a Google Drive thumbnail or a signed URL for Supabase files.
   */
  async function getThumbnailUrl(bucket: string, path: string, mimeType?: string): Promise<string> {
    // For Google Drive files, use the thumbnail endpoint
    if (bucket === 'google-drive' || path.startsWith('google-drive/')) {
      const fileId = extractGoogleDriveFileId(path)
      if (fileId) {
        // Google Drive thumbnail - works directly in img tags
        return `https://drive.google.com/thumbnail?id=${fileId}&sz=w400`
      }
    }
    
    // For regular files, use signed URL
    return getSignedUrl(bucket, path)
  }

  return { listFiles, getSignedUrl, getThumbnailUrl }
}