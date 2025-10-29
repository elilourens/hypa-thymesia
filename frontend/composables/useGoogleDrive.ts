import { ref, readonly } from 'vue'

interface GoogleDriveFile {
  id: string
  name: string
  mimeType?: string
  [key: string]: any
}

export const useGoogleDrive = () => {
  console.log('useGoogleDrive composable loaded')
  
  const error = ref('')
  const success = ref('')
  const loading = ref(false)
  const files = ref<GoogleDriveFile[]>([])
  const googleLinked = ref(false)

  const refreshGoogleToken = async (supabaseAccessToken: string) => {
    try {
      console.log('Attempting to refresh Google token...')
      const response = await fetch('http://localhost:8000/api/v1/refresh-google-token', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        throw new Error('Failed to refresh Google token')
      }

      console.log('Token refreshed successfully')
      return await response.json()
    } catch (err) {
      console.error('Refresh error:', err)
      throw err
    }
  }

  const getGoogleDriveToken = async (supabaseAccessToken: string) => {
    try {
      console.log('Getting Google token from backend...')
      const response = await fetch('http://localhost:8000/api/v1/google-drive-token', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        }
      })

      console.log('Backend response status:', response.status)

      if (!response.ok) {
        const errorData = await response.json()
        console.log('Backend error:', errorData)
        throw new Error(errorData.detail || 'Failed to retrieve Google token')
      }

      const data = await response.json()
      console.log('Retrieved token successfully')
      const { access_token } = data
      return access_token
    } catch (err) {
      console.error('Error in getGoogleDriveToken:', err)
      throw err
    }
  }

  const saveGoogleToken = async (
    supabaseAccessToken: string,
    accessToken: string,
    refreshToken?: string | null,
    expiresAt?: string
  ) => {
    try {
      const response = await fetch('http://localhost:8000/api/v1/save-google-token', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          access_token: accessToken,
          refresh_token: refreshToken || undefined,
          expires_at: expiresAt
        })
      })

      if (!response.ok) {
        throw new Error('Failed to save Google token')
      }

      return await response.json()
    } catch (err) {
      throw err
    }
  }

  const listGoogleDriveFiles = async (googleAccessToken: string, supabaseAccessToken: string, pageSize: number = 100, pageToken?: string): Promise<any> => {
    try {
      console.log('Calling Google Drive API...')
      console.log('Token (first 30 chars):', googleAccessToken.substring(0, 30) + '...')
      console.log('Token length:', googleAccessToken.length)
      
      const params = new URLSearchParams({
        pageSize: pageSize.toString(),
        spaces: 'drive',
        fields: 'files(id,name,mimeType,createdTime,modifiedTime,webViewLink,size),nextPageToken',
        q: 'trashed=false'
      })
      
      if (pageToken) {
        params.append('pageToken', pageToken)
      }
      
      let response = await fetch(
        `https://www.googleapis.com/drive/v3/files?${params.toString()}`,
        {
          headers: {
            Authorization: `Bearer ${googleAccessToken}`
          }
        }
      )

      console.log('Google API response status:', response.status)

      // If we get 401 from Google, try refreshing the token
      if (response.status === 401) {
        console.log('Got 401 from Google, attempting refresh...')
        try {
          const refreshResult = await refreshGoogleToken(supabaseAccessToken)
          console.log('Refresh successful')
          
          const newToken = await getGoogleDriveToken(supabaseAccessToken)
          console.log('Got new token, retrying API call...')
          
          response = await fetch(
            `https://www.googleapis.com/drive/v3/files?${params.toString()}`,
            {
              headers: {
                Authorization: `Bearer ${newToken}`
              }
            }
          )
          
          console.log('Retry response status:', response.status)
        } catch (refreshErr) {
          console.log('Refresh failed:', refreshErr)
          throw new Error('Token expired and refresh failed. Please relink your Google account.')
        }
      }

      if (!response.ok) {
        const errorData = await response.json()
        console.log('Google API error:', errorData)
        throw new Error(`Failed to fetch Drive files: ${errorData.error?.message || 'Unknown error'}`)
      }

      const filesData = await response.json()
      console.log('Files retrieved:', filesData.files?.length || 0)
      console.log('Has next page:', !!filesData.nextPageToken)
      return filesData
    } catch (err) {
      console.error('Error in listGoogleDriveFiles:', err)
      throw err
    }
  }

  const fetchAllGoogleDriveFiles = async (supabaseAccessToken: string) => {
    error.value = ''
    success.value = ''
    loading.value = true
    files.value = []

    try {
      console.log('Starting fetchAllGoogleDriveFiles...')
      const googleToken = await getGoogleDriveToken(supabaseAccessToken)
      console.log('Got Google token, now listing files...')
      
      let allFiles: GoogleDriveFile[] = []
      let nextPageToken: string | undefined = undefined
      let pageCount = 0

      // Keep fetching pages until there are no more
      do {
        pageCount++
        console.log(`Fetching page ${pageCount}...`)
        
        const filesData = await listGoogleDriveFiles(googleToken, supabaseAccessToken, 100, nextPageToken)
        
        allFiles = allFiles.concat(filesData.files || [])
        nextPageToken = filesData.nextPageToken
        
        console.log(`Page ${pageCount}: got ${filesData.files?.length || 0} files (total: ${allFiles.length})`)
      } while (nextPageToken)

      files.value = allFiles
      success.value = `Found ${allFiles.length} files in your Google Drive`
      console.log('Success! Total files:', allFiles.length)
      return allFiles
    } catch (err: unknown) {
      console.error('Final error:', err)
      if (err instanceof Error) {
        error.value = `Failed to access Google Drive: ${err.message}`
      } else {
        error.value = `Failed to access Google Drive: ${String(err)}`
      }
      return null
    } finally {
      loading.value = false
    }
  }

  const checkGoogleLinked = async (supabaseAccessToken: string) => {
    try {
      const response = await fetch('http://localhost:8000/api/v1/google-linked', {
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        }
      })

      const data = await response.json()
      googleLinked.value = data.linked
      return data.linked
    } catch (err) {
      console.error('Error checking Google link status:', err)
      googleLinked.value = false
      return false
    }
  }

  const unlinkGoogle = async (supabaseAccessToken: string) => {
    error.value = ''
    success.value = ''
    
    try {
      const response = await fetch('http://localhost:8000/api/v1/unlink-google', {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        throw new Error('Failed to unlink Google')
      }

      googleLinked.value = false
      success.value = 'Google account unlinked successfully'
      return await response.json()
    } catch (err) {
      console.error('unlinkGoogle error:', err)
      if (err instanceof Error) {
        error.value = `Failed to unlink: ${err.message}`
      } else {
        error.value = 'Failed to unlink Google account'
      }
      throw err
    }
  }

  const linkGoogleAccount = async (client: any, supabaseAccessToken: string) => {
    console.log('=== linkGoogleAccount called ===')
    error.value = ''
    success.value = ''

    try {
      let subscription: any

      // Set up auth state change listener BEFORE initiating the link
      const { data } = client.auth.onAuthStateChange(
        async (event: string, session: any) => {
          console.log('Auth state changed:', event)
          
          if (event === 'SIGNED_IN' && session?.provider_token) {
            console.log('Captured provider token from auth state change')
            console.log('Has refresh token:', !!session.provider_refresh_token)
            
            try {
              const { data: { session: currentSession } } = await client.auth.getSession()
              
              if (currentSession?.access_token) {
                const expiresAt = session.expires_at 
                  ? new Date(session.expires_at * 1000).toISOString() 
                  : undefined
                
                console.log('Saving Google token with:')
                console.log('- Access token (first 20 chars):', session.provider_token.substring(0, 20) + '...')
                console.log('- Refresh token present:', !!session.provider_refresh_token)
                console.log('- Expires at:', expiresAt)
                
                await saveGoogleToken(
                  currentSession.access_token,
                  session.provider_token,
                  session.provider_refresh_token || undefined,
                  expiresAt
                )
                
                success.value = 'Google account linked successfully!'
                googleLinked.value = true
                console.log('Token saved, googleLinked set to true')
                
                // Unsubscribe after successful save
                subscription?.unsubscribe()
              } else {
                throw new Error('No current session access token')
              }
            } catch (err) {
              console.error('Failed to save token:', err)
              error.value = 'Linked but failed to save token. Please try again.'
              subscription?.unsubscribe()
            }
          }
        }
      )
      
      subscription = data.subscription

      // Now initiate the link
      const { error: linkError } = await client.auth.linkIdentity({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/dashboard/link`,
          scopes: [
            'https://www.googleapis.com/auth/drive.readonly',
            'https://www.googleapis.com/auth/drive.metadata.readonly'
          ],
          queryParams: {
            access_type: 'offline',
            prompt: 'consent'
          }
        }
      })

      if (linkError) {
        console.error('linkIdentity error:', linkError)
        error.value = linkError.message
        subscription?.unsubscribe()
      }
    } catch (err) {
      console.error('linkGoogleAccount error:', err)
      error.value = 'An error occurred while linking your account'
    }
    
    console.log('=== linkGoogleAccount finished ===')
  }

  return {
    error: readonly(error),
    success: readonly(success),
    loading: readonly(loading),
    files: readonly(files),
    googleLinked: readonly(googleLinked),
    getGoogleDriveToken,
    saveGoogleToken,
    listGoogleDriveFiles,
    fetchGoogleDriveFiles: fetchAllGoogleDriveFiles,
    checkGoogleLinked,
    unlinkGoogle,
    refreshGoogleToken,
    linkGoogleAccount
  }
}

export const useAddGoogleDriveFile = () => {
  const loading = ref(false)
  const error = ref('')
  const success = ref('')

  const ingestGoogleDriveFileToSupabase = async (
    supabaseAccessToken: string,
    file: {
      id: string
      name: string
      mimeType?: string
      size?: number
      webViewLink?: string
    },
    groupId?: string,
    extractDeepEmbeds: boolean = true
  ) => {
    loading.value = true
    error.value = ''
    success.value = ''

    try {
      console.log('Ingesting Google Drive file to Supabase:', file.name)

      // FIX: Better size handling with warnings
      const fileSizeBytes = file.size ?? 0
      if (!file.size) {
        console.warn(`File "${file.name}" has no size metadata from Google Drive, using 0`)
      }

      const response = await fetch('http://localhost:8000/api/v1/ingest-google-drive-file', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          google_drive_id: file.id,
          google_drive_url: file.webViewLink || '',
          filename: file.name,
          mime_type: file.mimeType || 'application/octet-stream',
          size_bytes: fileSizeBytes,
          group_id: groupId || null,
          extract_deep_embeds: extractDeepEmbeds
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to ingest file')
      }

      const data = await response.json()
      success.value = `Successfully ingested "${file.name}" (${data.text_chunks_ingested} chunks${data.images_extracted ? `, ${data.images_extracted} images` : ''})`
      console.log('File ingested:', data)
      return data
    } catch (err) {
      console.error('Error ingesting Google Drive file:', err)
      if (err instanceof Error) {
        error.value = `Failed to ingest file: ${err.message}`
      } else {
        error.value = 'Failed to ingest Google Drive file'
      }
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    loading: readonly(loading),
    error: readonly(error),
    success: readonly(success),
    ingestGoogleDriveFileToSupabase
  }
}