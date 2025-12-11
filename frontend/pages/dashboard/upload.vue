<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useIngest } from '@/composables/useIngest'
import { useGroupsApi } from '@/composables/useGroups'
import { useQuota } from '@/composables/useQuota'
import GroupSelect from '@/components/GroupSelect.vue'
import BodyCard from '@/components/BodyCard.vue'
import GoogleDriveLinkCard from '@/components/GoogleDriveLinkCard.vue'
import OneDriveLinkCard from '@/components/OneDriveLinkCard.vue'

const { uploadFile } = useIngest()
const { createGroup } = useGroupsApi()
const { getQuota, isQuotaError, getQuotaFromError } = useQuota()

// UI state
const files = ref<File[]>([])
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const uploading = ref(false)
const quotaInfo = ref<{ current_count: number; max_files: number; remaining: number } | null>(null)

// Group mode: none, pick existing, or create new
const groupMode = ref<'none' | 'existing' | 'create'>('none')
const selectedGroupId = ref<string | null>(null)
const newGroupName = ref('')

// Enable upload only when conditions are met
const canUpload = computed(() => {
  if (!files.value.length || uploading.value) return false
  if (groupMode.value === 'create') return !!newGroupName.value.trim()
  if (groupMode.value === 'existing') return !!selectedGroupId.value
  return true
})

/** Resolve group by explicit mode */
async function resolveGroupId(): Promise<string | undefined> {
  if (groupMode.value === 'create') {
    const name = newGroupName.value.trim()
    if (!name) return undefined
    try {
      const g = await createGroup(name)
      selectedGroupId.value = g.id
      newGroupName.value = ''
      return g.id
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to create group'
      return undefined
    }
  }

  if (groupMode.value === 'existing') {
    return selectedGroupId.value || undefined
  }

  return undefined // "none"
}

async function loadQuota() {
  try {
    quotaInfo.value = await getQuota()
  } catch (e: any) {
    console.error('Failed to load quota:', e)
  }
}

async function doUpload(): Promise<void> {
  error.value = null
  success.value = null

  if (!files.value.length) {
    error.value = 'Pick at least one file'
    return
  }

  const groupId = await resolveGroupId()

  try {
    uploading.value = true
    const results = await Promise.allSettled(
      files.value.map(f => uploadFile(f, groupId))
    )
    const ok = results.filter(r => r.status === 'fulfilled').length
    const failed = results.length - ok
    const rejectedReasons = results
      .filter(r => r.status === 'rejected')
      .map(r => (r as PromiseRejectedResult).reason)

    // Check if any failures were due to quota
    const quotaError = rejectedReasons.find(e => isQuotaError(e))
    if (quotaError) {
      const quotaData = getQuotaFromError(quotaError)
      if (quotaData) {
        quotaInfo.value = quotaData
      }
      error.value = `Upload limit reached: You have ${quotaData?.current_count || 0} of ${quotaData?.max_files || 50} files. Upgrade your plan to upload more.`
    } else {
      if (ok > 0) success.value = `Uploaded ${ok} file${ok === 1 ? '' : 's'}`
      if (failed > 0) error.value = `Failed to upload ${failed} file${failed === 1 ? '' : 's'}`
    }

    if (ok === results.length) files.value = []

    // Refresh quota after successful uploads
    if (ok > 0) await loadQuota()
  } catch (e: any) {
    if (isQuotaError(e)) {
      const quotaData = getQuotaFromError(e)
      if (quotaData) {
        quotaInfo.value = quotaData
      }
      error.value = `Upload limit reached: You have ${quotaData?.current_count || 0} of ${quotaData?.max_files || 50} files. Upgrade your plan to upload more.`
    } else {
      error.value = e?.message ?? 'Upload failed'
    }
  } finally {
    uploading.value = false
  }
}

onMounted(() => {
  loadQuota()
})
</script>

<template>
  <BodyCard>
    <h1 class="font-semibold text-lg mb-4">Upload Files</h1>

    <div class="flex items-start gap-6">
      <!-- Left side: Files -->
      <div class="space-y-5">
        <UFileUpload
          v-model="files"
          multiple
          label="Drop your file here"
          layout="list"
          description="PDF, DOCX, TXT, PNG, JPG"
          class="w-96 min-h-48"
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
        />
      </div>

      <!-- Divider -->
      <USeparator orientation="vertical" class="h-auto self-stretch" size="lg"/>

      <!-- Right side: Groups and Upload -->
      <div class="flex-1 flex gap-4">
        <!-- Groups section -->
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
            <span v-if="files.length" class="text-xs text-gray-500">
              {{ files.length }} file{{ files.length === 1 ? '' : 's' }} selected
            </span>
          </div>

          <!-- Messages -->
          <p v-if="error" class="text-red-500 text-sm">{{ error }}</p>
          <p v-if="success" class="text-green-600 text-sm">{{ success }}</p>
        </div>

        <!-- Quota sidebar on the right -->
        <div v-if="quotaInfo" class="w-96 p-6 bg-zinc-900 rounded-lg self-start border border-zinc-800">
          <div class="flex items-center justify-between mb-3">
            <span class="text-sm font-medium text-zinc-200">
              File Storage
            </span>
          </div>

          <div class="text-center mb-4">
            <div class="text-4xl font-bold" :class="{
              'text-white': quotaInfo.remaining > 10,
              'text-orange-400': quotaInfo.remaining <= 10 && quotaInfo.remaining > 5,
              'text-red-400': quotaInfo.remaining <= 5
            }">
              {{ quotaInfo.current_count }}
            </div>
            <div class="text-sm text-zinc-400">
              of {{ quotaInfo.max_files }} files
            </div>
          </div>

          <UProgress
            :model-value="(quotaInfo.current_count / quotaInfo.max_files) * 100"
            :color="quotaInfo.remaining <= 5 ? 'error' : quotaInfo.remaining <= 10 ? 'warning' : 'primary'"
            size="md"
          />

          <div class="mt-4 text-center">
            <span class="text-sm text-zinc-400">
              {{ quotaInfo.remaining }} remaining
            </span>
          </div>

          <div v-if="quotaInfo.remaining <= 10" class="mt-4 text-center">
            <span class="text-sm font-medium" :class="{
              'text-orange-400': quotaInfo.remaining > 5,
              'text-red-400': quotaInfo.remaining <= 5
            }">
              {{ quotaInfo.remaining <= 5 ? '⚠️ Almost full!' : '⚠️ Running low' }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </BodyCard>

  <!-- Google Drive Import Section -->
  <BodyCard class="">
    <GoogleDriveLinkCard />
  </BodyCard>

  <!-- OneDrive Import Section -->
  <BodyCard class="">
    <OneDriveLinkCard />
  </BodyCard>
</template>

