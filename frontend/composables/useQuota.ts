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
    current_count: number  // Current page count
    max_files: number      // Maximum pages allowed
    remaining: number      // Pages remaining
    over_limit: number     // Pages over limit
    is_over_limit: boolean
    can_upload: boolean
    percentage_used: number
  }

  /**
   * Get user's current page quota information
   */
  async function getQuota(): Promise<QuotaInfo> {
    try {
      const headers = await authHeaders()
      return await $fetch<QuotaInfo>(`${API_BASE}/user-settings/quota-status`, {
        method: 'GET',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.message || err?.message || 'Failed to fetch quota')
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
    return message.includes('file upload limit') || message.includes('page upload limit') || message.includes('file_limit_reached')
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
    isQuotaError,
    getQuotaFromError,
  }
}
