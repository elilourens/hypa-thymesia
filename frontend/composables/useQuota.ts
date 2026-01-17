/**
 * Composable for managing user file quota
 */
export function useQuota() {
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

  interface QuotaInfo {
    current_count: number
    max_files: number
    remaining: number
    over_limit: number
    is_over_limit: boolean
    can_upload: boolean
    percentage_used: number
  }

  /**
   * Calculate file tokens needed for a video based on duration
   * 5 minutes = 1 token
   */
  function calculateVideoTokens(durationSeconds: number): number {
    const MINUTES_PER_TOKEN = 5
    if (durationSeconds <= 0) return 1
    return Math.max(1, Math.ceil(durationSeconds / (MINUTES_PER_TOKEN * 60)))
  }

  /**
   * Get user's current file quota information
   */
  async function getQuota(): Promise<QuotaInfo> {
    try {
      const headers = await authHeaders()
      return await $fetch<QuotaInfo>(`${API_BASE}/user/quota`, {
        method: 'GET',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.message || err?.message || 'Failed to fetch quota')
    }
  }

  /**
   * Update user's max files limit (typically called after payment)
   */
  async function updateMaxFiles(maxFiles: number): Promise<any> {
    try {
      const headers = {
        'Content-Type': 'application/json',
        ...(await authHeaders()),
      }
      return await $fetch(`${API_BASE}/user/max-files`, {
        method: 'PATCH',
        headers,
        body: { max_files: maxFiles },
      })
    } catch (err: any) {
      throw new Error(err?.data?.message || err?.message || 'Failed to update limit')
    }
  }

  /**
   * Parse error to check if it's a quota limit error
   */
  function isQuotaError(error: any): boolean {
    if (!error) return false

    // Check if error contains quota-related information
    const errorData = error?.data || error
    const errorDetail = errorData?.detail || errorData

    if (typeof errorDetail === 'object' && errorDetail?.error === 'file_limit_reached') {
      return true
    }

    // Check error message
    const message = error?.message || error?.data?.message || String(error)
    return message.includes('file upload limit') || message.includes('file_limit_reached')
  }

  /**
   * Extract quota info from error response
   */
  function getQuotaFromError(error: any): QuotaInfo | null {
    const errorData = error?.data || error
    const errorDetail = errorData?.detail || errorData

    if (typeof errorDetail === 'object' && errorDetail?.current_count !== undefined) {
      return {
        current_count: errorDetail.current_count,
        max_files: errorDetail.max_files,
        remaining: errorDetail.remaining || 0,
        over_limit: errorDetail.over_limit || 0,
        is_over_limit: errorDetail.over_limit > 0,
        can_upload: errorDetail.current_count < errorDetail.max_files,
        percentage_used: Math.min(100, (errorDetail.current_count / errorDetail.max_files) * 100)
      }
    }

    return null
  }

  return {
    getQuota,
    updateMaxFiles,
    isQuotaError,
    getQuotaFromError,
    calculateVideoTokens,
  }
}
