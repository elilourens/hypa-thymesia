import { ref, readonly, computed } from 'vue'

interface OneDriveFile {
  id: string
  name: string
  mimeType?: string
  createdTime?: string
  modifiedTime?: string
  webViewLink?: string
  size?: number
}

export const useOneDrive = () => {
  // ========================================================================
  // State
  // ========================================================================

  const error = ref<string>('')
  const success = ref<string>('')
  const loading = ref<boolean>(false)
  const files = ref<OneDriveFile[]>([])
  const microsoftLinked = ref<boolean>(false)
  const hasCheckedLink = ref<boolean>(false)

  // ========================================================================
  // Computed
  // ========================================================================

  const isInitialized = computed(() => hasCheckedLink.value)

  // ========================================================================
  // Core Token Management
  // ========================================================================

  /**
   * Save Microsoft tokens to backend after linking.
   * Called when user completes OAuth flow.
   */
  const saveMicrosoftToken = async (
    supabaseAccessToken: string,
    microsoftAccessToken: string,
    refreshToken?: string,
    expiresAt?: string
  ): Promise<void> => {
    try {
      const response = await fetch(
        'http://localhost:8000/api/v1/save-microsoft-token',
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            access_token: microsoftAccessToken,
            refresh_token: refreshToken || undefined,
            expires_at: expiresAt
          })
        }
      )

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to save token')
      }

      microsoftLinked.value = true
      success.value = 'Microsoft account linked successfully!'
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to save token'
      throw err
    }
  }

  /**
   * Check if we have provider tokens in session and save them.
   * Called on page mount after OAuth redirect.
   * Only processes tokens if the Azure provider was just linked.
   */
  const saveProviderTokensFromSession = async (
    supabaseClient: any
  ): Promise<boolean> => {
    try {
      const { data: { session } } = await supabaseClient.auth.getSession()

      console.log('[useOneDrive] Checking session for provider tokens:', {
        hasSession: !!session,
        hasAccessToken: !!session?.access_token,
        hasProviderToken: !!(session as any)?.provider_token,
        hasRefreshToken: !!(session as any)?.provider_refresh_token
      })

      // If we have provider tokens, check if they're for Azure (Microsoft)
      if (session && (session as any)?.provider_token) {
        const providerToken = (session as any).provider_token

        console.log('[useOneDrive] Provider token preview:', providerToken.substring(0, 10) + '...')

        // Additional check: Microsoft tokens start with "EwB" or "eyJ"
        // Google tokens start with "ya29."
        if (providerToken.startsWith('ya29.')) {
          console.log('[useOneDrive] Provider token appears to be a Google token (wrong prefix), skipping')
          return false
        }

        // Check if the URL has a 'code' parameter (indicating OAuth redirect just happened)
        const urlParams = new URLSearchParams(window.location.search)
        const hasCodeParam = urlParams.has('code')

        if (!hasCodeParam) {
          console.log('[useOneDrive] No OAuth code in URL, skipping token save (not a fresh redirect)')
          return false
        }

        // Get user identities to verify Azure identity exists
        const identitiesResult = await supabaseClient.auth.getUserIdentities()
        let identities: any[] = []
        if (identitiesResult?.data?.identities) {
          identities = identitiesResult.data.identities
        } else if (Array.isArray(identitiesResult)) {
          identities = identitiesResult
        } else if (identitiesResult?.identities) {
          identities = identitiesResult.identities
        }

        // Only process if Azure identity exists (this is Microsoft/OneDrive)
        const hasAzureIdentity = identities.some((id: any) => id.provider === 'azure')

        if (!hasAzureIdentity) {
          console.log('[useOneDrive] Provider token is not for Azure (no Azure identity), skipping')
          return false
        }

        console.log('[useOneDrive] Found valid Azure provider tokens in session, saving...')

        const microsoftTokenExpiresAt = new Date(Date.now() + 3600 * 1000).toISOString()

        await saveMicrosoftToken(
          session.access_token!,
          (session as any).provider_token,
          (session as any).provider_refresh_token,
          microsoftTokenExpiresAt
        )

        console.log('[useOneDrive] Tokens saved successfully from session!')

        // Clear URL params after successful save to prevent other composables from trying to process the same tokens
        const url = new URL(window.location.href)
        url.searchParams.delete('code')
        window.history.replaceState({}, '', url.toString())

        return true
      }

      return false
    } catch (err) {
      console.error('[useOneDrive] Error saving tokens from session:', err)
      error.value = 'Failed to save OAuth tokens'
      return false
    }
  }

  // ========================================================================
  // Link/Unlink Management
  // ========================================================================

  /**
   * Link a new Microsoft account via OAuth.
   * Sets up listener for OAuth tokens and initiates Supabase link flow.
   */
  const linkMicrosoftAccount = async (
    supabaseClient: any,
    supabaseAccessToken: string,
    forceConsent: boolean = false
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

              // Calculate Microsoft token expiration time (typically 1 hour = 3600 seconds)
              const microsoftTokenExpiresAt = new Date(Date.now() + 3600 * 1000).toISOString()

              // Save tokens to backend
              await saveMicrosoftToken(
                currentSession.access_token,
                session.provider_token,
                session.provider_refresh_token,
                microsoftTokenExpiresAt
              )

              success.value = 'Microsoft account linked successfully!'
              microsoftLinked.value = true

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

      // Build query params
      const queryParams: any = {
        access_type: 'offline', // Always request refresh token
        tenant: 'common', // Use common tenant for multi-tenant support
        prompt: forceConsent ? 'consent' : 'select_account' // Show account picker unless forcing consent
      }

      // Initiate the OAuth link with Supabase (Azure provider)
      const { error: linkError } = await supabaseClient.auth.linkIdentity({
        provider: 'azure',
        options: {
          redirectTo: `${window.location.origin}/dashboard/upload`,
          scopes: 'openid email profile User.Read Files.Read.All Sites.Read.All offline_access',
          queryParams
        }
      })

      if (linkError) {
        error.value = linkError.message
        subscription?.unsubscribe()
        throw linkError
      }
    } catch (err) {
      if (!(err instanceof Error) || !error.value) {
        error.value = 'Failed to link Microsoft account'
      }
      throw err
    }
  }

  /**
   * Unlink Microsoft account from both Supabase Auth and backend storage.
   */
  const unlinkMicrosoft = async (
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

      // Find the Azure identity (Microsoft)
      const azureIdentity = identities.find(
        (id: any) => id.provider === 'azure'
      )

      if (azureIdentity) {
        // Unlink from Supabase Auth
        const { error: unlinkError } = await supabaseClient.auth.unlinkIdentity(
          azureIdentity
        )

        if (unlinkError) {
          throw new Error(unlinkError.message)
        }
      }

      // Delete tokens from backend
      const response = await fetch(
        'http://localhost:8000/api/v1/unlink-microsoft',
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

      microsoftLinked.value = false
      success.value = 'Microsoft account unlinked successfully'
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
   * Check if user has Microsoft account linked.
   * Run this on app mount to restore state.
   */
  const checkMicrosoftLinked = async (
    supabaseAccessToken: string
  ): Promise<boolean> => {
    try {
      const response = await fetch(
        'http://localhost:8000/api/v1/microsoft-linked',
        {
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          }
        }
      )

      const data = await response.json()
      microsoftLinked.value = data.linked
      hasCheckedLink.value = true
      return data.linked
    } catch (err) {
      console.error('Error checking Microsoft link:', err)
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
        'http://localhost:8000/api/v1/microsoft-needs-consent',
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
   * Fetch files from OneDrive with pagination support.
   * Backend automatically handles token refresh.
   */
  const fetchOneDriveFiles = async (
    supabaseAccessToken: string,
    pageSize: number = 100,
    nextLink?: string
  ): Promise<{ files: OneDriveFile[], nextLink?: string }> => {
    error.value = ''
    success.value = ''
    loading.value = true

    try {
      const params = new URLSearchParams({
        page_size: pageSize.toString()
      })

      if (nextLink) {
        params.append('next_link', nextLink)
      }

      const response = await fetch(
        `http://localhost:8000/api/v1/onedrive-files?${params.toString()}`,
        {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${supabaseAccessToken}`,
            'Content-Type': 'application/json'
          }
        }
      )

      if (response.status === 401) {
        error.value = 'Microsoft token expired or invalid. Please relink your account.'
        microsoftLinked.value = false
        return { files: [] }
      }

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to fetch files')
      }

      const data = await response.json()
      const filesList = data.files || []

      files.value = filesList
      success.value = `Found ${filesList.length} files in your OneDrive`

      return {
        files: filesList,
        nextLink: data.nextLink
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      error.value = `Failed to fetch OneDrive files: ${message}`
      return { files: [] }
    } finally {
      loading.value = false
    }
  }

  /**
   * Ingest a OneDrive file using the backend API.
   * Downloads and processes the file.
   */
  const ingestOneDriveFile = async (
    supabaseAccessToken: string,
    fileData: {
      onedrive_id: string
      onedrive_url: string
      filename: string
      mime_type: string
      size_bytes: number
      extract_deep_embeds?: boolean
    }
  ): Promise<any> => {
    try {
      const response = await fetch(
        'http://localhost:8000/api/v1/ingest-onedrive-file',
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
      throw new Error(`Failed to ingest OneDrive file: ${message}`)
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
    microsoftLinked: computed(() => microsoftLinked.value),

    // Computed
    isInitialized: computed(() => hasCheckedLink.value),

    // Methods
    checkMicrosoftLinked,
    checkNeedsConsent,
    linkMicrosoftAccount,
    unlinkMicrosoft,
    fetchOneDriveFiles,
    saveMicrosoftToken,
    ingestOneDriveFile,
    saveProviderTokensFromSession
  }
}
