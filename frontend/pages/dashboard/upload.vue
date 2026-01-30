<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useToast } from '#ui/composables/useToast'
import { useDocumentUploadNotifications } from '@/composables/useDocumentUploadNotifications'
import { useGroupsApi } from '@/composables/useGroupsApi'
import { useQuota } from '@/composables/useQuota'
import GroupSelect from '@/components/GroupSelect.vue'
import BodyCard from '@/components/BodyCard.vue'
import UsageDisplay from '@/components/UsageDisplay.vue'

const { uploadMultipleAndNotify } = useDocumentUploadNotifications()
const { createGroup } = useGroupsApi()
const { getQuota } = useQuota()
const toast = useToast()

// UI state
const files = ref<File[]>([])
const uploading = ref(false)
const loadingQuota = ref(false)
const quotaInfo = ref<{
  current_page_count: number
  max_pages: number
  page_remaining: number
  page_over_limit: number
  page_is_over_limit: boolean
  page_can_upload: boolean
  page_percentage_used: number
  monthly_file_count: number
  max_monthly_files: number
  monthly_remaining: number
  monthly_can_upload: boolean
  monthly_percentage_used: number
  can_upload: boolean
} | null>(null)


// Group mode: none, pick existing, or create new
const groupMode = ref<'none' | 'existing' | 'create'>('none')
const selectedGroupId = ref<string | null>(null)
const newGroupName = ref('')

// Note: Tagging is handled automatically by Ragie's entity extraction

// Load quota on mount
onMounted(async () => {
  try {
    loadingQuota.value = true
    const quota = await getQuota()
    quotaInfo.value = quota
  } catch (e: any) {
    console.error('Failed to load quota:', e)
  } finally {
    loadingQuota.value = false
  }
})

// Enable upload only when conditions are met
const canUpload = computed(() => {
  if (!files.value.length || uploading.value) return false
  if (groupMode.value === 'create') return !!newGroupName.value.trim()
  if (groupMode.value === 'existing') return !!selectedGroupId.value
  // Check if user has reached quota limit
  if (quotaInfo.value && !quotaInfo.value.can_upload) return false
  return true
})

/** Resolve group by explicit mode */
async function resolveGroupId(): Promise<string | undefined> {
  if (groupMode.value === 'create') {
    const name = newGroupName.value.trim()
    if (!name) return undefined
    try {
      const g = await createGroup(name)
      selectedGroupId.value = g.group_id
      newGroupName.value = ''
      return g.group_id
    } catch (e: any) {
      toast.add({
        title: 'Failed to create group',
        description: e?.message,
        color: 'error',
        icon: 'i-lucide-alert-circle'
      })
      return undefined
    }
  }

  if (groupMode.value === 'existing') {
    return selectedGroupId.value || undefined
  }

  return undefined // "none"
}

// Note: In backend-ragie, all files count as 1 file (no token system)
// This is simpler than the old system

async function doUpload(): Promise<void> {
  if (!files.value.length) {
    toast.add({
      title: 'No files selected',
      description: 'Pick at least one file',
      color: 'error',
      icon: 'i-lucide-alert-circle'
    })
    return
  }

  const groupId = await resolveGroupId()

  try {
    uploading.value = true

    // Check quota before uploading
    if (quotaInfo.value && !quotaInfo.value.can_upload) {
      toast.add({
        title: 'Upload limit reached',
        description: `You have ${quotaInfo.value.current_page_count} of ${quotaInfo.value.max_pages} pages. Check the Usage tab for more details.`,
        color: 'error',
        icon: 'i-lucide-alert-triangle'
      })
      uploading.value = false
      return
    }

    // Upload all files - notifications handled by composable
    const uploadedIds = await uploadMultipleAndNotify(files.value, groupId)

    if (uploadedIds.length > 0) {
      files.value = []
      toast.add({
        title: 'Uploads started',
        description: `${uploadedIds.length} file${uploadedIds.length === 1 ? '' : 's'} queued for processing`,
        color: 'info',
        icon: 'i-lucide-upload'
      })
    }

    uploading.value = false
  } catch (e: any) {
    toast.add({
      title: 'Upload failed',
      description: e?.message ?? 'An unexpected error occurred',
      color: 'error',
      icon: 'i-lucide-alert-circle'
    })
    uploading.value = false
  }
}
</script>

<template>
  <BodyCard>
    <h1 class="font-semibold text-lg mb-4">Upload Files</h1>

    <div class="flex flex-col lg:flex-row lg:items-start gap-6">
      <!-- Left side: Files -->
      <div class="space-y-5">
        <UFileUpload
          v-model="files"
          multiple
          label="Drop your file here"
          layout="list"
          description="PDF, DOCX, PPT, PPTX, TXT, PNG, JPG, MP4, AVI, MOV"
          class="w-96 min-h-48"
          accept=".pdf,.docx,.ppt,.pptx,.txt,.png,.jpg,.jpeg,.mp4"
        />
      </div>

      <!-- Divider -->
      <USeparator orientation="vertical" class="hidden lg:block h-auto self-stretch" size="lg"/>

      <!-- Right side: Groups and Upload -->
      <div class="flex-1 space-y-3">
          <label class="block text-sm font-medium">Attach to a group</label>

          <!-- Mode switch -->
          <div class="flex gap-2" role="tablist" aria-label="Group mode">
            <UButton
              :variant="groupMode === 'none' ? 'subtle' : 'ghost'"
              @click="groupMode = 'none'"
              aria-pressed="groupMode === 'none'"
            >No group</UButton>
            <UButton
              :variant="groupMode === 'existing' ? 'subtle' : 'ghost'"
              @click="groupMode = 'existing'"
              aria-pressed="groupMode === 'existing'"
            >Choose existing</UButton>
            <UButton
              :variant="groupMode === 'create' ? 'subtle' : 'ghost'"
              @click="groupMode = 'create'"
              aria-pressed="groupMode === 'create'"
            >Create new</UButton>
          </div>

          <!-- Existing: use GroupSelect -->
          <div v-if="groupMode === 'existing'" class="flex items-center gap-2">
            <GroupSelect v-model="selectedGroupId" placeholder="Select a group…" />
          </div>

          <!-- Create: show input and button -->
          <div v-else-if="groupMode === 'create'" class="flex items-center gap-2">
            <UInput v-model="newGroupName" placeholder="New group name…" class="w-72" />
            <UButton
              :disabled="!newGroupName.trim() || uploading"
              @click="async () => { await resolveGroupId() }"
              variant="soft"
            >
              Create
            </UButton>
          </div>

          <!-- None: hint -->
          <p v-else class="text-xs text-gray-500">
            Files will be uploaded ungrouped. You can organize them later.
          </p>

          <!-- Actions -->
          <div class="flex items-center gap-3">
            <UButton :disabled="!canUpload" @click="doUpload">
              {{ uploading ? 'Uploading…' : 'Upload' }}
            </UButton>
            <div v-if="files.length" class="text-xs text-gray-500">
              <div>{{ files.length }} file{{ files.length === 1 ? '' : 's' }} selected</div>
            </div>
          </div>

          <!-- Messages -->
          <p v-if="quotaInfo && !quotaInfo.can_upload" class="text-red-500 text-sm">
            You've reached your storage limit. Upgrade your plan to upload more files.
          </p>
      </div>
    </div>
  </BodyCard>

  <!-- Usage Display Card -->
  <BodyCard class="mt-6">
    <UsageDisplay :quota-info="quotaInfo" :loading="loadingQuota" />
  </BodyCard>
</template>

