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
      let response = await fetch('http://localhost:8000/api/v1/google-drive-token', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        }
      })

      console.log('Backend response status:', response.status)

      if (response.status === 401) {
        console.log('Token expired (401), attempting refresh...')
        try {
          await refreshGoogleToken(supabaseAccessToken)
          
          response = await fetch('http://localhost:8000/api/v1/google-drive-token', {
            method: 'GET',
            headers: {
              'Authorization': `Bearer ${supabaseAccessToken}`,
              'Content-Type': 'application/json'
            }
          })
          
          console.log('After refresh, backend response status:', response.status)
        } catch (refreshErr) {
          console.log('Refresh failed:', refreshErr)
          throw new Error('Token expired and refresh failed. Please relink your Google account.')
        }
      }

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

  const listGoogleDriveFiles = async (googleAccessToken: string, pageSize: number = 10) => {
    try {
      console.log('Calling Google Drive API...')
      console.log('Token (first 30 chars):', googleAccessToken.substring(0, 30) + '...')
      console.log('Token starts with ya29:', googleAccessToken.startsWith('ya29'))
      console.log('Token length:', googleAccessToken.length)
      
      const response = await fetch(
        `https://www.googleapis.com/drive/v3/files?pageSize=${pageSize}`,
        {
          headers: {
            Authorization: `Bearer ${googleAccessToken}`
          }
        }
      )

      console.log('Google API response status:', response.status)

      if (!response.ok) {
        const errorData = await response.json()
        console.log('Google API error:', errorData)
        throw new Error(`Failed to fetch Drive files: ${errorData.error?.message || 'Unknown error'}`)
      }

      const filesData = await response.json()
      console.log('Files retrieved:', filesData.files?.length || 0)
      return filesData
    } catch (err) {
      console.error('Error in listGoogleDriveFiles:', err)
      throw err
    }
  }

  const fetchGoogleDriveFiles = async (supabaseAccessToken: string) => {
    error.value = ''
    success.value = ''
    loading.value = true
    files.value = []

    try {
      console.log('Starting fetchGoogleDriveFiles...')
      const googleToken = await getGoogleDriveToken(supabaseAccessToken)
      console.log('Got Google token, now listing files...')
      
      const filesData = await listGoogleDriveFiles(googleToken)
      
      files.value = filesData.files || []
      success.value = `Found ${filesData.files?.length || 0} files in your Google Drive`
      console.log('Success! Files:', files.value)
      return filesData
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
      return data.linked
    } catch (err) {
      return false
    }
  }

  const unlinkGoogle = async (supabaseAccessToken: string) => {
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

      return await response.json()
    } catch (err) {
      throw err
    }
  }

  return {
    error: readonly(error),
    success: readonly(success),
    loading: readonly(loading),
    files: readonly(files),
    getGoogleDriveToken,
    saveGoogleToken,
    listGoogleDriveFiles,
    fetchGoogleDriveFiles,
    checkGoogleLinked,
    unlinkGoogle,
    refreshGoogleToken
  }
}