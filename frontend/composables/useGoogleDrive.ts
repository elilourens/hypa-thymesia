import { ref, readonly, computed, onUnmounted } from 'vue'
import type { SyncResponse } from '~/types/google-drive'

interface GoogleDriveFile {
  id: string
  name: string
  mimeType?: string
  createdTime?: string
  modifiedTime?: string
  webViewLink?: string
  size?: number
}

export const useGoogleDrive = () => {
  // ========================================================================
  // Configuration
  // ========================================================================

  const config = useRuntimeConfig()
  const apiBase = config.public.apiBase || 'http://localhost:8000'

  // ========================================================================
  // State
  // ========================================================================

  const error = ref<string>('')
  const success = ref<string>('')
  const loading = ref<boolean>(false)
  const files = ref<GoogleDriveFile[]>([])
  const googleLinked = ref<boolean>(false)
  const hasCheckedLink = ref<boolean>(false)

  // AbortControllers for cancelling requests
  const abortControllers = ref<Map<string, AbortController>>(new Map())

  // ========================================================================
  // Computed
  // ========================================================================

  const isInitialized = computed(() => hasCheckedLink.value)

  // ========================================================================
  // AbortController Helpers
  // ========================================================================

  const getAbortController = (key: string): AbortSignal => {
    // Cancel previous request with same key
    abortControllers.value.get(key)?.abort()

    // Create new controller
    const controller = new AbortController()
    abortControllers.value.set(key, controller)
    return controller.signal
  }

  const cleanup = () => {
    // Abort all pending requests
    abortControllers.value.forEach(controller => controller.abort())
    abortControllers.value.clear()
  }

  // Cleanup on composable disposal
  if (typeof window !== 'undefined') {
    onUnmounted(() => {
      cleanup()
    })
  }

  // ========================================================================
  // Core Token Management
  // ========================================================================

  /**
   * Save Google tokens to backend after linking.
   * Called when user completes OAuth flow.
   */
  const saveGoogleToken = async (
    supabaseAccessToken: string,
    googleAccessToken: string,
    refreshToken?: string,
    expiresAt?: string
  ): Promise<void> => {
    try {
      const response = await fetch(
        `${apiBase}/save-google-token`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            access_token: googleAccessToken,
            refresh_token: refreshToken || undefined,
            expires_at: expiresAt
          })
        }
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to save token')
      }

      googleLinked.value = true
      success.value = 'Google account linked successfully!'
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to save token'
      throw err
    }
  }

  /**
   * Check if we have provider tokens in session and save them.
   * Called on page mount after OAuth redirect.
   * Only processes tokens if the Google provider was just linked.
   */
  const saveProviderTokensFromSession = async (
    supabaseClient: any
  ): Promise<boolean> => {
    try {
      const { data: { session } } = await supabaseClient.auth.getSession()

      console.log('[useGoogleDrive] Checking session for provider tokens:', {
        hasSession: !!session,
        hasAccessToken: !!session?.access_token,
        hasProviderToken: !!(session as any)?.provider_token,
        hasRefreshToken: !!(session as any)?.provider_refresh_token
      })

      // If we have provider tokens, check if they're for Google
      if (session && (session as any)?.provider_token) {
        const providerToken = (session as any).provider_token

        // Check token prefix: Google tokens ALWAYS start with "ya29."
        // Microsoft tokens start with "EwB" or "eyJ"
        if (!providerToken.startsWith('ya29.')) {
          console.log('[useGoogleDrive] Provider token does not appear to be a Google token (wrong prefix), skipping')
          return false
        }

        // Get user identities to verify Google identity exists
        const identitiesResult = await supabaseClient.auth.getUserIdentities()
        let identities: any[] = []
        if (identitiesResult?.data?.identities) {
          identities = identitiesResult.data.identities
        } else if (Array.isArray(identitiesResult)) {
          identities = identitiesResult
        } else if (identitiesResult?.identities) {
          identities = identitiesResult.identities
        }

        // Only process if Google identity exists
        const hasGoogleIdentity = identities.some((id: any) => id.provider === 'google')

        if (!hasGoogleIdentity) {
          console.log('[useGoogleDrive] Provider token is not for Google (no Google identity), skipping')
          return false
        }

        console.log('[useGoogleDrive] Found valid Google provider tokens in session!')

        // Mark as linked - tokens are in session and will be saved to backend when connecting a folder
        googleLinked.value = true

        // Clear URL params after successful OAuth to clean up URL
        const url = new URL(window.location.href)
        url.searchParams.delete('code')
        window.history.replaceState({}, '', url.toString())

        console.log('[useGoogleDrive] Google linked successfully!')

        return true
      }

      return false
    } catch (err) {
      console.error('[useGoogleDrive] Error saving tokens from session:', err)
      error.value = 'Failed to save OAuth tokens'
      return false
    }
  }

  // ========================================================================
  // Link/Unlink Management
  // ========================================================================

  /**
   * Link a new Google account via OAuth.
   * Sets up listener for OAuth tokens and initiates Supabase link flow.
   */
  const linkGoogleAccount = async (
    supabaseClient: any,
    supabaseAccessToken: string
  ): Promise<void> => {
    error.value = ''
    success.value = ''

    try {
      // Validate origin against allowed URLs
      const config = useRuntimeConfig()
      const allowedOrigins = [
        config.public.appUrl || window.location.origin,
        'http://localhost:3000',
        'http://127.0.0.1:3000'
      ]

      if (!allowedOrigins.includes(window.location.origin)) {
        throw new Error('Invalid origin - OAuth redirect not allowed from this domain')
      }

      // Build query params - always force consent to ensure refresh token
      // Google only returns refresh tokens on first auth OR when prompt=consent is used
      const queryParams: any = {
        access_type: 'offline', // Always request refresh token
        prompt: 'consent' // Force consent screen to ensure we get a refresh token
      }

      // Build redirect URL with validated origin
      const redirectTo = `${window.location.origin}/dashboard/connections`

      // Initiate the OAuth link with Supabase
      const { error: linkError } = await supabaseClient.auth.linkIdentity({
        provider: 'google',
        options: {
          redirectTo,
          scopes: [
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/drive.metadata.readonly'
          ],
          queryParams
        }
      })

      if (linkError) {
        error.value = linkError.message
        throw linkError
      }
    } catch (err) {
      if (!(err instanceof Error) || !error.value) {
        error.value = 'Failed to link Google account'
      }
      throw err
    }
  }

  /**
   * Unlink Google account from both Supabase Auth and backend storage.
   * Revokes tokens with Google.
   */
  const unlinkGoogle = async (
    supabaseClient: any,
    supabaseAccessToken: string
  ): Promise<void> => {
    error.value = ''
    success.value = ''

    try {
      // Get user identities from Supabase Auth
      const identitiesResult = await supabaseClient.auth.getUserIdentities()

      // Handle different response formats from Supabase SDK
      let identities: any[] = []
      if (identitiesResult?.data?.identities) {
        identities = identitiesResult.data.identities
      } else if (Array.isArray(identitiesResult)) {
        identities = identitiesResult
      } else if (identitiesResult?.identities) {
        identities = identitiesResult.identities
      }

      // Find the Google identity
      const googleIdentity = identities.find(
        (id: any) => id.provider === 'google'
      )

      if (!googleIdentity) {
        throw new Error('No Google identity found to unlink')
      }

      // Unlink from Supabase Auth
      const { error: unlinkError } = await supabaseClient.auth.unlinkIdentity(
        googleIdentity
      )

      if (unlinkError) {
        throw new Error(unlinkError.message)
      }

      // Delete tokens from backend and revoke with Google
      const response = await fetch(
        `${apiBase}/unlink-google`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          }
        }
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to unlink')
      }

      googleLinked.value = false
      success.value = 'Google account unlinked successfully'
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      error.value = `Failed to unlink: ${message}`
      throw err
    }
  }

  // ========================================================================
  // File Fetching
  // ========================================================================

  /**
   * Check if user has Google account linked.
   * Run this on app mount to restore state.
   */
  const checkGoogleLinked = async (
    supabaseAccessToken: string
  ): Promise<boolean> => {
    try {
      const response = await fetch(
        `${apiBase}/google-linked`,
        {
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          }
        }
      )

      const data = await response.json()
      googleLinked.value = data.linked
      hasCheckedLink.value = true
      return data.linked
    } catch (err) {
      console.error('Error checking Google link:', err)
      hasCheckedLink.value = true
      return false
    }
  }

  /**
   * Check if user needs to consent to get refresh token.
   * Returns true if user should be prompted with consent screen.
   */
  const checkNeedsConsent = async (
    supabaseAccessToken: string
  ): Promise<boolean> => {
    try {
      const response = await fetch(
        `${apiBase}/google-needs-consent`,
        {
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          }
        }
      )

      const data = await response.json()
      return data.needs_consent || false
    } catch (err) {
      console.error('Error checking consent need:', err)
      return false
    }
  }

  /**
   * Fetch files from Google Drive with pagination support.
   * Backend automatically handles token refresh.
   */
  const fetchGoogleDriveFiles = async (
    supabaseAccessToken: string,
    pageSize: number = 100,
    pageToken?: string
  ): Promise<{ files: GoogleDriveFile[], nextPageToken?: string }> => {
    error.value = ''
    success.value = ''
    loading.value = true

    try {
      const params = new URLSearchParams({
        page_size: pageSize.toString()
      })

      if (pageToken) {
        params.append('page_token', pageToken)
      }

      const response = await fetch(
        `${apiBase}/google-drive-files?${params.toString()}`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          },
          signal: getAbortController('fetchGoogleDriveFiles')
        }
      )

      if (response.status === 401) {
        error.value = 'Google token expired or invalid. Please relink your account.'
        googleLinked.value = false
        return { files: [] }
      }

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to fetch files')
      }

      const data = await response.json()
      const filesList = data.files || []
      
      files.value = filesList
      success.value = `Found ${filesList.length} files in your Google Drive`
      
      return {
        files: filesList,
        nextPageToken: data.nextPageToken
      }
    } catch (err) {
      // Silent abort
      if (err instanceof Error && err.name === 'AbortError') {
        return { files: [] }
      }
      const message = err instanceof Error ? err.message : 'Unknown error'
      error.value = `Failed to fetch Google Drive files: ${message}`
      return { files: [] }
    } finally {
      loading.value = false
    }
  }

  /**
   * Ingest a Google Drive file using the backend API.
   * Downloads and processes the file.
   */
  const ingestGoogleDriveFile = async (
    supabaseAccessToken: string,
    fileData: {
      google_drive_id: string
      google_drive_url: string
      filename: string
      mime_type: string
      size_bytes: number
      extract_deep_embeds?: boolean
      group_id?: string
      enable_tagging?: boolean
    }
  ): Promise<any> => {
    try {
      const response = await fetch(
        `${apiBase}/ingest-google-drive-file`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(fileData)
        }
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to ingest file')
      }

      return await response.json()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      throw new Error(`Failed to ingest Google Drive file: ${message}`)
    }
  }

  // ========================================================================
  // Google Drive Folder Sync
  // ========================================================================

  /**
   * Connect a Google Drive folder for automatic syncing.
   */
  const connectGoogleDriveFolder = async (
    supabaseAccessToken: string,
    googleAccessToken: string,
    googleRefreshToken: string,
    tokenExpiresIn: number,
    folderId: string,
    folderName: string,
    groupId?: string
  ): Promise<void> => {
    try {
      const response = await fetch(
        `${apiBase}/google-drive/connect-folder`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            folder_id: folderId,
            folder_name: folderName,
            group_id: groupId,
            access_token: googleAccessToken,
            refresh_token: googleRefreshToken,
            token_expires_in: tokenExpiresIn
          })
        }
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to connect folder')
      }

      const data = await response.json()
      success.value = data.message
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to connect folder'
      throw err
    }
  }

  /**
   * Get sync configuration.
   */
  const getSyncConfig = async (
    supabaseAccessToken: string
  ): Promise<any> => {
    try {
      const response = await fetch(
        `${apiBase}/google-drive/sync-config`,
        {
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          }
        }
      )

      if (!response.ok) {
        throw new Error('Failed to get sync config')
      }

      return await response.json()
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to get sync config'
      return null
    }
  }

  /**
   * Disconnect Google Drive sync.
   */
  const disconnectGoogleDrive = async (
    supabaseAccessToken: string
  ): Promise<void> => {
    try {
      const response = await fetch(
        `${apiBase}/google-drive/disconnect`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          }
        }
      )

      if (!response.ok) {
        throw new Error('Failed to disconnect')
      }

      success.value = 'Google Drive sync disconnected'
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to disconnect'
      throw err
    }
  }

  /**
   * Manually trigger sync (called when user clicks "Sync Now").
   */
  const triggerManualSync = async (
    supabaseAccessToken: string
  ): Promise<SyncResponse> => {
    loading.value = true
    error.value = ''
    success.value = ''

    try {
      const response = await fetch(
        `${apiBase}/google-drive/sync`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          },
          signal: getAbortController('triggerManualSync')
        }
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to sync')
      }

      const data = await response.json()
      success.value = `Synced ${data.files_processed} new files`
      return {
        status: data.status || 'success',
        files_processed: data.files_processed,
        files_failed: data.files_failed,
        total_files: data.total_files,
        failed_files: data.failed_files
      }
    } catch (err) {
      // Silent abort
      if (err instanceof Error && err.name === 'AbortError') {
        return {
          status: 'error',
          files_processed: 0,
          files_failed: 0,
          total_files: 0,
          failed_files: []
        }
      }
      error.value = err instanceof Error ? err.message : 'Failed to sync'
      throw err
    } finally {
      loading.value = false
    }
  }

  // ========================================================================
  // Public API
  // ========================================================================

  return {
    // State (as computed to avoid readonly issues)
    error: computed(() => error.value),
    success: computed(() => success.value),
    loading: computed(() => loading.value),
    files: computed(() => [...files.value]), // Spread to ensure mutability
    googleLinked: computed(() => googleLinked.value),

    // Computed
    isInitialized: computed(() => hasCheckedLink.value),

    // Methods
    checkGoogleLinked,
    checkNeedsConsent,
    linkGoogleAccount,
    unlinkGoogle,
    fetchGoogleDriveFiles,
    saveGoogleToken,
    ingestGoogleDriveFile,
    saveProviderTokensFromSession,
    connectGoogleDriveFolder,
    getSyncConfig,
    disconnectGoogleDrive,
    triggerManualSync,
    cleanup
  }
}