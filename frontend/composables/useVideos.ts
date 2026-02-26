/**
 * Composable for managing video uploads to Supabase Storage via backend-ragie
 */

export interface VideoItem {
  id: string
  filename: string
  storage_path: string
  file_size_bytes: number
  duration_seconds: number | null
  fps: number | null
  width: number | null
  height: number | null
  processing_status: 'queued' | 'processing' | 'completed' | 'failed'
  chunk_count: number | null
  group_id: string | null
  group_name: string | null
  created_at: string
  updated_at: string
}

export interface VideoListResponse {
  items: VideoItem[]
  total: number
  has_more: boolean
}

export interface VideoStatusResponse {
  id: string
  processing_status: 'queued' | 'processing' | 'completed' | 'failed'
  chunk_count: number | null
  filename: string
}

export function useVideos() {
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
   * Upload a video file to Supabase Storage
   */
  async function uploadVideo(
    file: File,
    groupId?: string
  ): Promise<VideoItem> {
    try {
      const headers = await authHeaders()
      const fd = new FormData()
      fd.append('file', file)
      if (groupId) fd.append('group_id', groupId)

      return await $fetch<VideoItem>(`${API_BASE}/videos/upload`, {
        method: 'POST',
        headers,
        body: fd,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Video upload failed')
    }
  }

  /**
   * List all videos for the current user
   */
  async function listVideos(params: {
    page?: number
    page_size?: number
    group_id?: string | null
    sort?: 'created_at' | 'filename' | 'duration_seconds'
    dir?: 'asc' | 'desc'
  } = {}): Promise<VideoListResponse> {
    try {
      const headers = await authHeaders()
      const sp = new URLSearchParams()

      if (params.page) sp.set('page', String(params.page))
      if (params.page_size) sp.set('page_size', String(params.page_size))
      if (params.group_id) sp.set('group_id', params.group_id)
      if (params.sort) sp.set('sort', params.sort)
      if (params.dir) sp.set('dir', params.dir)

      const url = sp.toString() ? `${API_BASE}/videos/list?${sp.toString()}` : `${API_BASE}/videos/list`

      return await $fetch<VideoListResponse>(url, {
        method: 'GET',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to load videos')
    }
  }

  /**
   * Get a single video's details
   */
  async function getVideo(videoId: string): Promise<VideoItem> {
    try {
      const headers = await authHeaders()
      return await $fetch<VideoItem>(`${API_BASE}/videos/${videoId}`, {
        method: 'GET',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to get video')
    }
  }

  /**
   * Check video processing status
   */
  async function getVideoStatus(videoId: string): Promise<VideoStatusResponse> {
    try {
      const headers = await authHeaders()
      return await $fetch<VideoStatusResponse>(`${API_BASE}/videos/${videoId}`, {
        method: 'GET',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to get video status')
    }
  }

  /**
   * Watch video processing status via Server-Sent Events (SSE)
   * Real-time updates without polling
   */
  async function watchVideoStatus(
    videoId: string,
    onUpdate?: (status: VideoStatusResponse) => void,
    onError?: (error: string) => void,
    timeout?: number,
    onDelete?: (documentId: string) => void
  ): Promise<() => void> {
    const t = await token()
    const eventSource = new EventSource(
      `${API_BASE}/videos/${videoId}/updates`,
      { headers: { Authorization: `Bearer ${t}` } }
    )

    let timeoutId: ReturnType<typeof setTimeout> | null = null
    let closed = false

    const cleanup = () => {
      if (!closed) {
        closed = true
        eventSource.close()
        if (timeoutId) clearTimeout(timeoutId)
      }
    }

    // Handle incoming SSE messages
    eventSource.addEventListener('message', async (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.event === 'connected') {
          // Connection established, now fetch initial status
          const status = await getVideoStatus(videoId)
          if (onUpdate) onUpdate(status)

          // Set timeout if specified
          if (timeout) {
            timeoutId = setTimeout(() => {
              if (onError) onError('Video processing timeout')
              cleanup()
            }, timeout)
          }
        } else if (data.event === 'status_update') {
          // Status update from webhook
          const status = await getVideoStatus(videoId)
          if (onUpdate) onUpdate(status)

          // Stop watching if processing is complete or failed
          if (status.processing_status === 'completed' || status.processing_status === 'ready' || status.processing_status === 'failed') {
            cleanup()
          }
        } else if (data.event === 'document_deleted') {
          // Document was deleted
          if (onDelete) onDelete(data.document_id)
          cleanup()
        }
      } catch (err: any) {
        console.error('Error parsing SSE message:', err)
      }
    })

    // Handle connection errors
    eventSource.onerror = () => {
      if (onError) onError('Connection lost')
      cleanup()
    }

    // Return cleanup function
    return cleanup
  }

  /**
   * Poll video processing status until completed or failed
   * Legacy fallback - use watchVideoStatus for real-time updates
   */
  async function pollVideoStatus(
    videoId: string,
    onUpdate?: (status: VideoStatusResponse) => void,
    maxAttempts: number = 120,
    intervalMs: number = 1000
  ): Promise<VideoStatusResponse> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const status = await getVideoStatus(videoId)

      if (onUpdate) {
        onUpdate(status)
      }

      if (status.processing_status === 'completed' || status.processing_status === 'ready' || status.processing_status === 'failed') {
        return status
      }

      await new Promise(resolve => setTimeout(resolve, intervalMs))
    }

    throw new Error('Video processing timeout')
  }

  /**
   * Delete a video
   */
  async function deleteVideo(videoId: string): Promise<void> {
    try {
      const headers = await authHeaders()
      await $fetch(`${API_BASE}/videos/${videoId}`, {
        method: 'DELETE',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to delete video')
    }
  }

  return {
    uploadVideo,
    listVideos,
    getVideo,
    getVideoStatus,
    watchVideoStatus,
    pollVideoStatus,
    deleteVideo,
  }
}
