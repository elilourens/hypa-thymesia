<script setup lang="ts">
import { onMounted, ref, computed, watch } from 'vue'
import { useIngest } from '@/composables/useIngest'
import { useGroupsApi, type Group } from '@/composables/useGroups'

const { uploadFile } = useIngest()
const { listGroups, createGroup } = useGroupsApi()

// UI state
const files = ref<File[]>([])
const error = ref<string | null>(null)
const success = ref<string | null>(null)
const uploading = ref(false)

// Groups
const groups = ref<Group[]>([])
const loadingGroups = ref(false)

// Group mode: none, pick existing, or create new
const groupMode = ref<'none' | 'existing' | 'create'>('none')
const selectedGroupId = ref<string | undefined>(undefined)
const newGroupName = ref('')

// Derived sorted groups
const sortedGroups = computed(() =>
  [...groups.value].sort(
    (a, b) =>
      (a.sort_index ?? 0) - (b.sort_index ?? 0) ||
      a.name.localeCompare(b.name)
  )
)

// Feed USelectMenu items
const selectOptions = computed(() =>
  sortedGroups.value.map(g => ({
    label: g.name ?? '(unnamed)',
    value: g.id,
  }))
)

// Enable upload only when conditions are met
const canUpload = computed(() => {
  if (!files.value.length || uploading.value) return false
  if (groupMode.value === 'create') return !!newGroupName.value.trim()
  if (groupMode.value === 'existing') return !!selectedGroupId.value
  return true
})

async function refreshGroups() {
  loadingGroups.value = true
  error.value = null
  try {
    groups.value = await listGroups()
  } catch (e: any) {
    error.value = e?.message || 'Failed to load groups'
    console.error('[groups error]', e)
  } finally {
    loadingGroups.value = false
  }
}

// Keep selectedGroupId consistent if groups change
watch(groups, () => {
  if (selectedGroupId.value && !groups.value.some(g => g.id === selectedGroupId.value)) {
    selectedGroupId.value = undefined
  }
})

onMounted(refreshGroups)

/** Resolve group by explicit mode */
async function resolveGroupId(): Promise<string | undefined> {
  if (groupMode.value === 'create') {
    const name = newGroupName.value.trim()
    if (!name) return undefined
    try {
      const g = await createGroup(name)
      groups.value = [g, ...groups.value]
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

    if (ok > 0) success.value = `Uploaded ${ok} file${ok === 1 ? '' : 's'}`
    if (failed > 0) error.value = `Failed to upload ${failed} file${failed === 1 ? '' : 's'}`
    if (ok === results.length) files.value = []
  } catch (e: any) {
    error.value = e?.message ?? 'Upload failed'
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="space-y-5 max-w-xl">
    <h1 class="font-semibold text-lg">Upload Files</h1>

    <!-- Files -->
    <UFileUpload
      v-model="files"
      multiple
      label="Drop your file here"
      layout="list"
      description="PDF, DOCX, TXT, PNG, JPG"
      class="w-96 min-h-48"
      accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
    />

    <!-- Groups -->
    <ClientOnly>
      <div class="space-y-3">
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

        <!-- Existing: show select -->
        <div v-if="groupMode === 'existing'" class="flex items-center gap-2">
          <USelectMenu
            v-model="selectedGroupId"
            :items="selectOptions"
            value-key="value"
            placeholder="Select a group…"
            :loading="loadingGroups"
            :search-input="{ placeholder: 'Search groups…' }"
            icon="i-lucide-users"
            class="w-72"
            @update:open="(open) => { if (open && !groups.length) refreshGroups() }"
          >
            <template #empty>
              <span class="text-muted">No groups found</span>
            </template>
          </USelectMenu>
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
      </div>

      <template #fallback>
        <div class="space-y-2">
          <div class="h-6 w-48 bg-gray-100 rounded" />
          <div class="h-10 w-72 bg-gray-100 rounded" />
        </div>
      </template>
    </ClientOnly>

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
</template>
