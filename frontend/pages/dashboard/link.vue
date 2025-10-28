<script setup lang="ts">
const client = useSupabaseClient()
const { data: { user } } = await client.auth.getUser()

const linking = ref(false)
const listing = ref(false)
const unlinking = ref(false)
const googleLinked = ref(false)
const localError = ref('')
const localSuccess = ref('')
const { 
  fetchGoogleDriveFiles, 
  checkGoogleLinked, 
  unlinkGoogle,
  saveGoogleToken,
  error,
  success,
  files
} = useGoogleDrive()

// Check if Google is already linked
const checkLinkStatus = async () => {
  const { data: { session } } = await client.auth.getSession()
  if (session?.access_token) {
    googleLinked.value = await checkGoogleLinked(session.access_token)
  }
}

onMounted(async () => {
  await checkLinkStatus()
})

async function linkGoogleAccount() {
  console.log('=== linkGoogleAccount called ===')
  linking.value = true
  localError.value = ''
  localSuccess.value = ''

  try {
    const { data: { subscription } } = client.auth.onAuthStateChange(
      async (event, session) => {
        if (session?.provider_token) {
          console.log('Captured provider token')
          console.log('Has refresh token:', !!session.provider_refresh_token)
          try {
            const { data: { session: currentSession } } = await client.auth.getSession()
            
            if (currentSession?.access_token) {
              const expiresAt = session.expires_at 
                ? new Date(session.expires_at * 1000).toISOString() 
                : undefined
              
              await saveGoogleToken(
                currentSession.access_token,
                session.provider_token,
                session.provider_refresh_token || undefined,
                expiresAt
              )
              
              localSuccess.value = 'Google account linked successfully!'
              googleLinked.value = true
              console.log('Token saved, googleLinked set to true')
            }
          } catch (err) {
            console.error('Failed to save token:', err)
            localError.value = 'Linked but failed to save token. Please try again.'
          }
          
          subscription?.unsubscribe()
        }
      }
    )

    const { error: err } = await client.auth.linkIdentity({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/dashboard/link`,
        scopes: 'https://www.googleapis.com/auth/drive.readonly',
        queryParams: {
          access_type: 'offline',
          prompt: 'consent'
        }
      }
    })

    if (err) {
      localError.value = err.message
      subscription?.unsubscribe()
    }
  } catch (err) {
    console.error('linkGoogleAccount error:', err)
    localError.value = 'An error occurred while linking your account'
  }

  linking.value = false
  console.log('=== linkGoogleAccount finished ===')
}

async function handleListFiles() {
  console.log('=== handleListFiles called ===')
  listing.value = true
  localError.value = ''
  localSuccess.value = ''
  console.log('listing.value set to true')
  
  try {
    const { data: { session } } = await client.auth.getSession()
    console.log('Got session:', !!session?.access_token)
    
    if (session?.access_token) {
      console.log('Calling fetchGoogleDriveFiles...')
      await fetchGoogleDriveFiles(session.access_token)
      console.log('fetchGoogleDriveFiles completed')
      console.log('Files returned:', files.value.length)
    } else {
      console.log('No session access token!')
      localError.value = 'No session access token'
    }
  } catch (err) {
    console.error('handleListFiles error:', err)
    localError.value = `Error: ${err}`
  }
  
  listing.value = false
  console.log('=== handleListFiles finished ===')
}

async function handleUnlinkGoogle() {
  console.log('=== handleUnlinkGoogle called ===')
  unlinking.value = true
  localError.value = ''
  localSuccess.value = ''

  try {
    const { data: { session } } = await client.auth.getSession()
    if (session?.access_token) {
      await unlinkGoogle(session.access_token)
      localSuccess.value = 'Google account unlinked'
      googleLinked.value = false
      
      await new Promise(resolve => setTimeout(resolve, 500))
      await checkLinkStatus()
    }
  } catch (err: unknown) {
    console.error('handleUnlinkGoogle error:', err)
    if (err instanceof Error) {
      localError.value = `Failed to unlink: ${err.message}`
    } else {
      localError.value = 'Failed to unlink Google account'
    }
  }

  unlinking.value = false
  console.log('=== handleUnlinkGoogle finished ===')
}
</script>

<template>
  <BodyCard>
    <div class="space-y-4">
      <div v-if="!googleLinked" class="space-y-2">
        <p class="text-sm text-gray-600">Connect your Google account to access your Drive files</p>
        <UButton
          @click="linkGoogleAccount"
          :loading="linking"
          icon="i-lucide-chrome"
        >
          Link Google Account
        </UButton>
      </div>

      <div v-else class="space-y-2">
        <div class="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-200">
          <div class="flex items-center gap-2">
            <UIcon name="i-lucide-check-circle" class="text-green-600" />
            <span class="text-sm font-medium text-green-700">Google account linked</span>
          </div>
        </div>

        <UButton
          @click="handleListFiles"
          :loading="listing"
          variant="soft"
          icon="i-lucide-folder-open"
        >
          List Google Drive Files
        </UButton>

        <!-- Display files if any -->
        <div v-if="files.length > 0" class="space-y-2">
          <p class="text-sm font-medium text-gray-700">Google Drive Files ({{ files.length }}):</p>
          <div class="space-y-1 max-h-64 overflow-y-auto border rounded p-2 bg-gray-50">
            <div v-for="file in files" :key="file.id" class="p-2 bg-white rounded text-sm border-l-4 border-blue-400">
              <div class="font-medium">{{ file.name }}</div>
              <div class="text-xs text-gray-500">{{ file.mimeType }}</div>
            </div>
          </div>
        </div>

        <UButton
          @click="handleUnlinkGoogle"
          :loading="unlinking"
          variant="ghost"
          
          icon="i-lucide-unlink"
        >
          Unlink Google Account
        </UButton>
      </div>

      <UAlert v-if="localError || error" color="error" :title="localError || error" icon="i-lucide-alert-circle" />
      <UAlert v-if="localSuccess || success" color="success" :title="localSuccess || success" icon="i-lucide-check-circle" />
    </div>
  </BodyCard>
</template>