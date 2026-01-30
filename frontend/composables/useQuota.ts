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
    // Page quota
    current_page_count: number
    max_pages: number
    page_remaining: number
    page_over_limit: number
    page_is_over_limit: boolean
    page_can_upload: boolean
    page_percentage_used: number
    // Monthly file quota
    monthly_file_count: number
    max_monthly_files: number
    monthly_remaining: number
    monthly_can_upload: boolean
    monthly_percentage_used: number
    // Overall
    can_upload: boolean
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
    return (
      message.includes('file upload limit') ||
      message.includes('page upload limit') ||
      message.includes('monthly file') ||
      message.includes('file_limit_reached')
    )
  }

  /**
   * Extract quota info from error response
   */
  function getQuotaFromError(error: any): QuotaInfo | null {
    const errorData = error?.data || error
    const errorDetail = errorData?.detail || errorData

    if (typeof errorDetail === 'object' && errorDetail?.current_page_count !== undefined) {
      const current_page_count = errorDetail.current_page_count || 0
      const max_files = errorDetail.max_files || 200
      const monthly_file_count = errorDetail.monthly_file_count || 0
      const max_monthly_files = errorDetail.max_monthly_files || 50

      return {
        current_page_count,
        max_pages: max_files,
        page_remaining: Math.max(0, max_files - current_page_count),
        page_over_limit: Math.max(0, current_page_count - max_files),
        page_is_over_limit: current_page_count > max_files,
        page_can_upload: current_page_count < max_files,
        page_percentage_used: Math.min(100, (current_page_count / max_files) * 100),
        monthly_file_count,
        max_monthly_files,
        monthly_remaining: Math.max(0, max_monthly_files - monthly_file_count),
        monthly_can_upload: monthly_file_count < max_monthly_files,
        monthly_percentage_used: Math.min(100, (monthly_file_count / max_monthly_files) * 100),
        can_upload: current_page_count < max_files && monthly_file_count < max_monthly_files
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
