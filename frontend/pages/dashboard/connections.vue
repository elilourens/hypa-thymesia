<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { useGoogleDrive } from '@/composables/useGoogleDrive'
import { useOneDrive } from '@/composables/useOneDrive'
import { useGooglePicker } from '@/composables/useGooglePicker'
import { useDocumentUploadNotifications } from '@/composables/useDocumentUploadNotifications'
import BodyCard from '@/components/BodyCard.vue'

const supabase = useSupabaseClient()
const user = useSupabaseUser()
const config = useRuntimeConfig()

const {
  connectGoogleDriveFolder,
  getSyncConfig,
  disconnectGoogleDrive,
  triggerManualSync,
  linkGoogleAccount,
  unlinkGoogle,
  saveProviderTokensFromSession: saveGoogleTokens,
  cleanup: cleanupGoogleDrive
} = useGoogleDrive()

const { openFolderPicker } = useGooglePicker()
const { saveProviderTokensFromSession: saveOneDriveTokens } = useOneDrive()
const { pollSyncedDocuments } = useDocumentUploadNotifications()

const syncConfig = ref<any>(null)
const syncing = ref(false)
const localError = ref('')
const localSuccess = ref('')
const googleLinked = ref(false) // This will be determined by the backend
const mounted = ref(true)

onMounted(async () => {
  try {
    // On page load after OAuth redirect, the session may contain provider tokens.
    // We need to verify them. It's safe to call both functions,
    // as they will internally check if the tokens belong to their provider.
    await saveGoogleTokens(supabase)
    if (!mounted.value) return

    await saveOneDriveTokens(supabase)
    if (!mounted.value) return

    if (!user.value) return

    const { data: { session } } = await supabase.auth.getSession()
    if (!session || !mounted.value) return

    // Check if Google is linked by checking user identities (no backend call needed)
    try {
      const identitiesResult = await supabase.auth.getUserIdentities()
      if (!mounted.value) return

      let identities: any[] = []

      if (identitiesResult && 'data' in identitiesResult && identitiesResult.data?.identities) {
        identities = identitiesResult.data.identities
      }

      if (mounted.value) {
        googleLinked.value = identities.some((id: any) => id.provider === 'google')
      }
    } catch (err) {
      console.error('[Connections] Error checking Google identity:', err)
      if (mounted.value) {
        googleLinked.value = false
      }
    }

    if (!mounted.value) return

    // If just returned from OAuth, show a success message
    if ((session as any).provider_token && (session as any).provider_token.startsWith('ya29.')) {
      const providerToken = (session as any).provider_token
      const providerRefreshToken = (session as any).provider_refresh_token

      if (providerToken && providerRefreshToken && mounted.value) {
        localSuccess.value = 'Google Drive connected! Now select a folder to sync.'
        googleLinked.value = true // Confirm linked after successful OAuth return
      }
    }

    // If linked, check for an existing sync configuration
    if (googleLinked.value && mounted.value) {
      syncConfig.value = await getSyncConfig(session.access_token)
    }
  } catch (err) {
    if (mounted.value) {
      localError.value = err instanceof Error ? err.message : 'Failed to initialize'
    }
  }
})

onUnmounted(() => {
  mounted.value = false
  cleanupGoogleDrive()
})

const handleLinkGoogle = async () => {
  localError.value = ''
  localSuccess.value = ''
  try {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) throw new Error('User not authenticated')
    // Use the composable function to link the account
    await linkGoogleAccount(supabase, session.access_token)
  } catch (err) {
    localError.value = err instanceof Error ? err.message : 'Failed to link Google account'
  }
}

const handleUnlinkGoogle = async () => {
  localError.value = ''
  localSuccess.value = ''
  try {
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) throw new Error('User not authenticated')
    // Use the composable function to unlink
    await unlinkGoogle(supabase, session.access_token)
    googleLinked.value = false
    localSuccess.value = 'Google account unlinked'
  } catch (err) {
    localError.value = err instanceof Error ? err.message : 'Failed to unlink Google account'
  }
}

const handleConnectFolder = async () => {
  localError.value = ''
  localSuccess.value = ''
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) {
    localError.value = 'Session expired. Please refresh the page.'
    return
  }

  // Get Google access token from session
  const providerToken = (session as any).provider_token
  const providerRefreshToken = (session as any).provider_refresh_token

  if (!providerToken || !providerToken.startsWith('ya29.')) {
    localError.value = 'No Google token found in session. Please re-link your account to select a folder.'
    return
  }

  if (!providerRefreshToken) { // The refresh token is crucial for sync
    localError.value = 'No refresh token found. Please unlink and re-link your Google account with consent.'
    return
  }

  // Open Google Picker - need to get the Google Client ID from environment
  const googleClientId = (config.public.googleClientId as string) || ''

  try {
    const folder = await openFolderPicker(
      providerToken,
      googleClientId
    )

    if (!folder) return  // User cancelled picker

    // Connect folder - calculate token expiry from session
    // Google tokens typically expire in 1 hour (3600 seconds)
    const tokenExpiresIn = (session as any).expires_in || 3600
    await connectGoogleDriveFolder(
      session.access_token,
      providerToken,
      providerRefreshToken,
      tokenExpiresIn,
      folder.id,
      folder.name
    )

    // Refresh sync config to show the new state
    syncConfig.value = await getSyncConfig(session.access_token)
    localSuccess.value = `Connected folder: ${folder.name}`
  } catch (err) {
    localError.value = err instanceof Error ? err.message : 'Failed to connect folder.'
  }
}

const handleDisconnect = async () => {
  localError.value = ''
  localSuccess.value = ''

  const { data: { session } } = await supabase.auth.getSession()
  if (!session) {
    localError.value = 'Session expired. Please refresh the page.'
    return
  }

  await disconnectGoogleDrive(session.access_token)
  syncConfig.value = null
  localSuccess.value = 'Google Drive sync disconnected'
}

const handleSyncNow = useDebounceFn(async () => {
  localError.value = ''
  localSuccess.value = ''
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) {
    localError.value = 'Session expired. Please refresh the page.'
    return
  }

  syncing.value = true
  try {
    const result = await triggerManualSync(session.access_token)
    // Refresh sync config to show updated last_sync_at
    syncConfig.value = await getSyncConfig(session.access_token)

    // Display comprehensive sync summary
    if (result.files_processed === 0 && (result.files_failed || 0) === 0) {
      localSuccess.value = 'Sync complete - no new files found'
    } else if ((result.files_failed || 0) === 0) {
      localSuccess.value = `Successfully synced ${result.files_processed} file${result.files_processed !== 1 ? 's' : ''}`
    } else if (result.files_processed === 0) {
      localError.value = `Sync failed - ${result.files_failed} file${result.files_failed !== 1 ? 's' : ''} had errors`
    } else {
      localSuccess.value = `Synced ${result.files_processed} file${result.files_processed !== 1 ? 's' : ''} successfully, ${result.files_failed} failed`
    }

    // Fetch recently synced files and start polling their status
    // This fetches page_count and chunks as Ragie processes them
    if (result.files_processed > 0 && syncConfig.value) {
      const { data: syncedFiles } = await supabase
        .from('google_drive_files')
        .select('ragie_document_id')
        .eq('sync_config_id', syncConfig.value.id)
        .not('ragie_document_id', 'is', null)
        .order('last_synced_at', { ascending: false })
        .limit(result.files_processed)

      if (syncedFiles && syncedFiles.length > 0) {
        const fileIds = (syncedFiles as any[])
          .map((f: any) => f.ragie_document_id)
          .filter((id: any): id is string => id !== null)

        if (fileIds.length > 0) {
          // Start polling these files in background
          pollSyncedDocuments(fileIds)
        }
      }
    }
  } catch (err) {
    localError.value = err instanceof Error ? err.message : 'Failed to sync'
  } finally {
    syncing.value = false
  }
}, 1000, { maxWait: 2000 })
</script>

<template>
  <BodyCard>
    <div class="space-y-6 max-w-4xl mx-auto">
      <h1 class="font-semibold text-xl">Connections</h1>

      <!-- Google Drive Section -->
      <div class="border rounded-lg p-6 space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="font-semibold text-lg">Google Drive</h2>
            <p class="text-sm text-foreground/70">
              Automatically sync files from a Google Drive folder
            </p>
          </div>

          <UButton
            v-if="!googleLinked"
            @click="handleLinkGoogle"
            color="primary"
          >
            Connect Google Drive
          </UButton>
        </div>

        <!-- Sync Config Display -->
        <div v-if="googleLinked && syncConfig" class="space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm font-medium">Syncing Folder</p>
              <p class="text-sm text-foreground/70">{{ syncConfig.folder_name }}</p>
            </div>
            <UButton
              @click="handleDisconnect"
              color="error"
              variant="outline"
              size="sm"
            >
              Disconnect
            </UButton>
          </div>

          <div class="text-xs text-foreground/50 space-y-1">
            <div>Last synced: {{ syncConfig.last_sync_at ? new Date(syncConfig.last_sync_at).toLocaleString() : 'Never' }}</div>
            <div>Files synced: {{ syncConfig.files_count }}</div>
          </div>

          <!-- Sync Now Button -->
          <UButton
            @click="handleSyncNow"
            :loading="syncing"
            :disabled="syncing"
            color="primary"
            icon="i-heroicons-arrow-path"
          >
            {{ syncing ? 'Syncing...' : 'Sync Now' }}
          </UButton>
        </div>

        <!-- Connect Folder Button -->
        <div v-else-if="googleLinked && !syncConfig">
          <UButton
            @click="handleConnectFolder"
            color="primary"
          >
            Select Folder to Sync
          </UButton>
        </div>

        <!-- Unlink Button (if linked but no folder) -->
        <div v-if="googleLinked && !syncConfig" class="mt-4">
          <UButton
            @click="handleUnlinkGoogle"
            color="error"
            variant="outline"
            size="sm"
          >
            Unlink Google Account
          </UButton>
        </div>
      </div>

      <!-- Error/Success Messages -->

      <UAlert v-if="localError" color="error" :description="localError" />
      <UAlert v-if="localSuccess" color="success" :description="localSuccess" />
    </div>
  </BodyCard>
</template>
