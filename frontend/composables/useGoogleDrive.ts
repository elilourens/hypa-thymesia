import { ref, readonly, computed } from 'vue'

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
  // State
  // ========================================================================
  
  const error = ref<string>('')
  const success = ref<string>('')
  const loading = ref<boolean>(false)
  const files = ref<GoogleDriveFile[]>([])
  const googleLinked = ref<boolean>(false)
  const hasCheckedLink = ref<boolean>(false)

  // ========================================================================
  // Computed
  // ========================================================================

  const isInitialized = computed(() => hasCheckedLink.value)

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
        'http://localhost:8000/api/v1/save-google-token',
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

      // If we have provider tokens, save them
      if (session && (session as any)?.provider_token) {
        console.log('[useGoogleDrive] Found provider tokens in session, saving...')

        const googleTokenExpiresAt = new Date(Date.now() + 3600 * 1000).toISOString()

        await saveGoogleToken(
          session.access_token!,
          (session as any).provider_token,
          (session as any).provider_refresh_token,
          googleTokenExpiresAt
        )

        console.log('[useGoogleDrive] Tokens saved successfully from session!')
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
      let subscription: any

      // Listen for auth state changes when linking
      const { data } = supabaseClient.auth.onAuthStateChange(
        async (event: string, session: any) => {
          // When linking (not signing in), we get provider_token in the session
          if (session?.provider_token) {
            try {
              const { data: { session: currentSession } } =
                await supabaseClient.auth.getSession()

              if (!currentSession?.access_token) {
                throw new Error('No session access token')
              }

              // Calculate Google token expiration time (typically 1 hour = 3600 seconds)
              // The session.expires_at is for Supabase session, not Google token
              // Google tokens typically expire in 3600 seconds (1 hour)
              const googleTokenExpiresAt = new Date(Date.now() + 3600 * 1000).toISOString()

              // Save tokens to backend
              await saveGoogleToken(
                currentSession.access_token,
                session.provider_token,
                session.provider_refresh_token,
                googleTokenExpiresAt
              )

              success.value = 'Google account linked successfully!'
              googleLinked.value = true

              // Clean up listener
              subscription?.unsubscribe()
            } catch (err) {
              error.value = 'Linked but failed to save token. Please try again.'
              subscription?.unsubscribe()
              throw err
            }
          }
        }
      )

      subscription = data.subscription

      // Initiate the OAuth link with Supabase
      const { error: linkError } = await supabaseClient.auth.linkIdentity({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/dashboard/link`,
          scopes: [
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/drive.metadata.readonly'
          ],
          queryParams: {
            access_type: 'offline', // Request refresh token
            //prompt: 'consent'
          }
        }
      })

      if (linkError) {
        error.value = linkError.message
        subscription?.unsubscribe()
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
        'http://localhost:8000/api/v1/unlink-google',
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
        'http://localhost:8000/api/v1/google-linked',
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
        `http://localhost:8000/api/v1/google-drive-files?${params.toString()}`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          }
        }
      )

      if (response.status === 401) {
        error.value = 'Google token expired. Attempting to relink...'
        googleLinked.value = false
        
        // Auto-retry link to refresh token
        try {
          const supabaseClient = useSupabaseClient()
          await linkGoogleAccount(supabaseClient, supabaseAccessToken)
          
          // Wait a moment then retry the fetch
          await new Promise(resolve => setTimeout(resolve, 1000))
          return fetchGoogleDriveFiles(supabaseAccessToken, pageSize, pageToken)
        } catch (linkErr) {
          throw new Error('Token expired and relink failed. Please link manually.')
        }
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
    }
  ): Promise<any> => {
    try {
      const response = await fetch(
        'http://localhost:8000/api/v1/ingest-google-drive-file',
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
    linkGoogleAccount,
    unlinkGoogle,
    fetchGoogleDriveFiles,
    saveGoogleToken,
    ingestGoogleDriveFile,
    saveProviderTokensFromSession
  }
}